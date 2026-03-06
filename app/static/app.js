/* Medienspiegel – Robust UI */

// Dropdown schliessen bei Klick ausserhalb
document.addEventListener('click', function(e) {
    document.querySelectorAll('.dropdown.open').forEach(function(d) {
        if (!d.contains(e.target)) d.classList.remove('open');
    });
});

// === Scroll-Animation (IntersectionObserver) ===
var _scrollObserver = null;

function initScrollAnimations() {
    if (_scrollObserver) _scrollObserver.disconnect();

    _scrollObserver = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                entry.target.classList.remove('scroll-hidden');
                entry.target.classList.add('scroll-visible');
                _scrollObserver.unobserve(entry.target);
            }
        });
    }, {
        threshold: 0.05,
        rootMargin: '0px 0px -30px 0px'
    });

    var cards = document.querySelectorAll('.article-card, .tweet-card');
    var staggerDelay = 0;

    cards.forEach(function(card) {
        if (card.dataset.scrollInit) return;
        card.dataset.scrollInit = '1';

        var rect = card.getBoundingClientRect();
        if (rect.top < window.innerHeight + 50) {
            // Karte ist im Viewport → gestaffelter Fade-in
            card.classList.add('scroll-hidden');
            var delay = staggerDelay;
            staggerDelay += 40;
            requestAnimationFrame(function() {
                setTimeout(function() {
                    card.classList.remove('scroll-hidden');
                    card.classList.add('scroll-visible');
                }, delay);
            });
        } else {
            // Karte ist ausserhalb → verstecken + beobachten
            card.classList.add('scroll-hidden');
            _scrollObserver.observe(card);
        }
    });
}


// === Button Loading States ===
function setButtonLoading(btn, loadingText) {
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spin">&#x21bb;</span> ' + (loadingText || 'Laden...');
}

function restoreButton(btn) {
    if (!btn) return;
    btn.disabled = false;
    if (btn.dataset.originalText) {
        btn.innerHTML = btn.dataset.originalText;
        delete btn.dataset.originalText;
    }
}


// === HTMX Event-Handler ===

// Loading-State fuer Buttons die HTMX-Requests ausloesen
document.body.addEventListener('htmx:beforeRequest', function(evt) {
    var trigger = evt.detail.elt;
    if (!trigger) return;

    // Nur Buttons mit hx-post/hx-get behandeln
    if (trigger.tagName === 'BUTTON' || trigger.classList.contains('btn')) {
        var text = 'Laden...';
        if (trigger.id === 'btn-collect' || trigger.textContent.indexOf('sammeln') >= 0) {
            text = 'Sammle...';
        } else if (trigger.textContent.indexOf('Zusammenfass') >= 0) {
            text = 'Fasse zusammen...';
        }
        setButtonLoading(trigger, text);
    }
});

// Button wiederherstellen nach Request
document.body.addEventListener('htmx:afterRequest', function(evt) {
    var trigger = evt.detail.elt;
    if (trigger && (trigger.tagName === 'BUTTON' || trigger.classList.contains('btn'))) {
        // Kurze Verzoegerung damit Swap zuerst passiert
        setTimeout(function() { restoreButton(trigger); }, 200);
    }
});

// Fehlerbehandlung bei HTMX-Requests
document.body.addEventListener('htmx:responseError', function(evt) {
    var trigger = evt.detail.elt;
    if (trigger) restoreButton(trigger);

    var status = evt.detail.xhr ? evt.detail.xhr.status : 0;
    var msg = 'Fehler beim Laden.';
    if (status === 0) {
        msg = 'Server nicht erreichbar. Bitte spaeter erneut versuchen.';
    } else if (status >= 500) {
        msg = 'Serverfehler (' + status + '). Bitte spaeter erneut versuchen.';
    }

    // Fehlermeldung einblenden
    var target = evt.detail.target;
    if (target) {
        var notice = document.createElement('div');
        notice.className = 'notice error';
        notice.setAttribute('role', 'alert');
        notice.textContent = msg;
        target.prepend(notice);

        // Auto-hide nach 8 Sekunden
        setTimeout(function() {
            notice.style.transition = 'opacity 0.3s';
            notice.style.opacity = '0';
            setTimeout(function() { notice.remove(); }, 300);
        }, 8000);
    }
});

// Sende-Fehler (Netzwerk-Fehler)
document.body.addEventListener('htmx:sendError', function(evt) {
    var trigger = evt.detail.elt;
    if (trigger) restoreButton(trigger);
});


// Themen-Gruppierung an/aus
function toggleGrouping() {
    var btn = document.getElementById('toggle-grouping');
    var list = document.getElementById('article-list');
    var groups = list.querySelectorAll('.topic-group');
    var isGrouped = btn.classList.contains('active');

    if (isGrouped) {
        btn.classList.remove('active');
        btn.textContent = 'Gruppiert';
        groups.forEach(function(g) {
            g.querySelector('.topic-group-header').style.display = 'none';
            g.style.marginBottom = '0';
        });
    } else {
        btn.classList.add('active');
        btn.textContent = 'Gruppiert';
        groups.forEach(function(g) {
            g.querySelector('.topic-group-header').style.display = '';
            g.style.marginBottom = '';
        });
    }
}

// Zusammenfassung auf-/zuklappen
function toggleSummary(toggleEl) {
    var container = toggleEl.closest('.ai-summary, .tweet-summary');
    if (!container) return;
    var isExpanded = container.classList.contains('expanded');
    if (isExpanded) {
        container.classList.remove('expanded');
        toggleEl.textContent = 'mehr';
    } else {
        container.classList.add('expanded');
        toggleEl.textContent = 'weniger';
    }
}

// Initialisiere Toggle-Sichtbarkeit (verstecke "mehr" bei kurzen Texten)
function initSummaryToggles() {
    document.querySelectorAll('.ai-summary, .tweet-summary').forEach(function(el) {
        if (el.dataset.initToggle) return;
        el.dataset.initToggle = '1';
        var textEl = el.querySelector('.summary-text');
        var toggleEl = el.querySelector('.summary-toggle');
        if (!textEl || !toggleEl) return;
        if (textEl.scrollHeight <= textEl.clientHeight + 2) {
            toggleEl.style.display = 'none';
        }
    });
}

// Alert-Panel auf-/zuklappen
function toggleAlertPanel() {
    var panel = document.getElementById('alerts-panel');
    var section = panel.closest('.alerts-section');
    if (section.classList.contains('open')) {
        section.classList.remove('open');
    } else {
        section.classList.add('open');
    }
}

// Twitter widgets.js laden (einmalig)
var _twttrLoaded = false;
function ensureTwitterWidgets() {
    if (_twttrLoaded) return;
    _twttrLoaded = true;
    var script = document.createElement('script');
    script.src = 'https://platform.twitter.com/widgets.js';
    script.async = true;
    script.charset = 'utf-8';
    document.head.appendChild(script);
}

// Alle Tweet-Embeds auf der Seite automatisch laden
function initTweetEmbeds() {
    var wraps = document.querySelectorAll('.tweet-embed-wrap[data-tweet-id]');
    if (wraps.length === 0) return;
    ensureTwitterWidgets();

    function renderAll() {
        if (!(window.twttr && window.twttr.widgets && window.twttr.widgets.createTweet)) {
            setTimeout(renderAll, 300);
            return;
        }
        wraps.forEach(function(wrap) {
            if (wrap.dataset.loaded) return;
            wrap.dataset.loaded = '1';
            var tweetId = wrap.dataset.tweetId;
            var handle = wrap.dataset.handle;
            var container = wrap.querySelector('.tweet-embed-content');
            if (!container) return;

            window.twttr.widgets.createTweet(tweetId, container, {
                theme: 'dark',
                dnt: true
            }).then(function(el) {
                if (!el) {
                    container.innerHTML = '<p style="color:#8899a6;font-size:0.8rem;padding:8px 0;">Post nicht verfuegbar. <a href="https://x.com/' + handle + '/status/' + tweetId + '" target="_blank" style="color:#1d9bf0;">Auf X ansehen</a></p>';
                }
            }).catch(function() {});
        });
    }
    renderAll();
}

// Nach HTMX-Swap und initial
document.body.addEventListener('htmx:afterSwap', function() {
    document.querySelectorAll('.dropdown.open').forEach(function(d) {
        d.classList.remove('open');
    });
    // Erfolgs-Meldungen auto-hide
    var notices = document.querySelectorAll('.notice.success');
    notices.forEach(function(notice) {
        setTimeout(function() {
            notice.style.transition = 'opacity 0.3s';
            notice.style.opacity = '0';
            setTimeout(function() { notice.remove(); }, 300);
        }, 5000);
    });
    initSummaryToggles();
    initTweetEmbeds();
    initScrollAnimations();
});

document.addEventListener('DOMContentLoaded', function() {
    initSummaryToggles();
    initTweetEmbeds();
    initScrollAnimations();
});
