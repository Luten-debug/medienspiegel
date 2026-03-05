/* Medienspiegel */

// Dropdown schliessen bei Klick ausserhalb
document.addEventListener('click', function(e) {
    document.querySelectorAll('.dropdown.open').forEach(function(d) {
        if (!d.contains(e.target)) d.classList.remove('open');
    });
});

// === Scroll-Animation (IntersectionObserver) ===
var _scrollObserver = null;

function initScrollAnimations() {
    // Observer fuer Karten die beim Scrollen einfliegen
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
        rootMargin: '0px 0px -20px 0px'
    });

    // Alle Karten beobachten die noch nicht sichtbar sind
    var staggerDelay = 0;
    document.querySelectorAll('.article-card, .tweet-card').forEach(function(card) {
        if (card.dataset.scrollInit) return;
        card.dataset.scrollInit = '1';

        // Karten die schon im Viewport sind gestaffelt einblenden
        var rect = card.getBoundingClientRect();
        if (rect.top < window.innerHeight + 80) {
            card.style.animationDelay = staggerDelay + 'ms';
            card.classList.add('scroll-visible');
            staggerDelay += 60;
        } else {
            // Karten ausserhalb: verstecken + beobachten
            card.classList.add('scroll-hidden');
            _scrollObserver.observe(card);
        }
    });
}


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
