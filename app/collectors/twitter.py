"""Twitter/X Collector - holt Tweets ueber mehrere Strategien mit Fallback."""

import re
import json
import html as htmlmod
import xml.etree.ElementTree as ET
import requests
from datetime import datetime, timedelta
from dateutil import parser as dateparser

from .base import BaseCollector, CollectedArticle

# Bekannte Accounts die ueber Tesla Giga Berlin posten
DEFAULT_ACCOUNTS = [
    'Gf4Tesla',       # Gigafactory Berlin News
    'alex_avoigt',    # Alex Voigt - Tesla/EV analyst
    'SawyerMerritt',  # Sawyer Merritt - Tesla news
    'Teslaconomics',  # Teslaconomics
    'TeslaEurope',    # Tesla Europe
    'Tesla',          # Tesla official
]

# Suchbegriffe um relevante Tweets zu filtern
RELEVANCE_KEYWORDS = [
    'giga berlin', 'gigafactory', 'gruenheide', 'grünheide',
    'giga factory', 'tesla berlin', 'tesla germany', 'tesla deutschland',
    'tesla brandenburg', 'gigaberlin', 'giga-berlin',
    'betriebsrat', 'ig metall', 'works council',
    'robotaxi', 'cybercab', 'model y', 'model 2',
    'giga', 'tesla',
]

# Nitter / Xcancel Instanzen (werden der Reihe nach probiert)
NITTER_INSTANCES = [
    'https://xcancel.com',
    'https://nitter.privacydev.net',
    'https://nitter.poast.org',
    'https://nitter.cz',
    'https://nitter.woodland.cafe',
]

# RSSHub Instanzen
RSSHUB_INSTANCES = [
    'https://rsshub.app',
    'https://rsshub.rssforever.com',
    'https://hub.slarker.me',
]


class TwitterCollector(BaseCollector):

    _is_twitter = True

    @property
    def name(self):
        return "X/Twitter"

    def is_available(self):
        twitter_config = self.config.get('twitter', {})
        return twitter_config.get('enabled', False)

    def collect(self, search_term, lang=None, country=None):
        """Sammle Tweets ueber mehrere Strategien mit Fallback."""
        twitter_config = self.config.get('twitter', {})
        accounts = twitter_config.get('accounts', DEFAULT_ACCOUNTS)
        max_tweets = twitter_config.get('max_tweets', 20)

        articles = []
        strategy_used = None

        for account in accounts:
            tweets = []

            # Strategie 1: Nitter/Xcancel RSS
            if not tweets:
                tweets = self._fetch_nitter_rss(account)
                if tweets:
                    strategy_used = strategy_used or 'nitter'

            # Strategie 2: RSSHub
            if not tweets:
                tweets = self._fetch_rsshub(account)
                if tweets:
                    strategy_used = strategy_used or 'rsshub'

            # Strategie 3: Twitter Syndication API (Legacy, oft blockiert)
            if not tweets:
                tweets = self._fetch_syndication(account)
                if tweets:
                    strategy_used = strategy_used or 'syndication'

            # Strategie 4: Google-Suche nach Tweets dieses Accounts
            if not tweets:
                tweets = self._fetch_via_google(account)
                if tweets:
                    strategy_used = strategy_used or 'google'

            for tweet in tweets:
                if self._is_relevant(tweet, search_term):
                    article = self._tweet_to_article(tweet, account, search_term, lang)
                    if article:
                        articles.append(article)

            if len(articles) >= max_tweets:
                break

        if strategy_used:
            print("  [TWITTER] {} Tweets via {} gesammelt".format(len(articles), strategy_used))
        else:
            print("  [TWITTER] Keine Tweets gefunden (alle Strategien fehlgeschlagen)")

        return articles[:max_tweets]

    # === Strategie 1: Nitter/Xcancel RSS ===

    def _fetch_nitter_rss(self, account):
        """Hole Tweets via Nitter RSS Feed (mehrere Instanzen)."""
        for instance in NITTER_INSTANCES:
            try:
                url = '{}/{}/rss'.format(instance, account)
                resp = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Accept': 'application/rss+xml, application/xml, text/xml',
                })
                if resp.status_code != 200:
                    continue

                tweets = self._parse_rss_feed(resp.text, account)
                if tweets:
                    return tweets
            except Exception:
                continue
        return []

    def _parse_rss_feed(self, xml_text, account):
        """Parse RSS/Atom Feed zu Tweet-Daten."""
        tweets = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        # RSS 2.0 Format
        items = root.findall('.//item')
        if not items:
            # Atom Format
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            items = root.findall('.//atom:entry', ns)

        for item in items[:20]:
            tweet = self._rss_item_to_tweet(item, account)
            if tweet:
                tweets.append(tweet)

        return tweets

    def _rss_item_to_tweet(self, item, account):
        """Konvertiere RSS Item zu Tweet-Dict."""
        # RSS 2.0 Tags
        title_el = item.find('title')
        link_el = item.find('link')
        desc_el = item.find('description')
        pubdate_el = item.find('pubDate')

        # Atom Fallback
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        if title_el is None:
            title_el = item.find('atom:title', ns)
        if link_el is None:
            link_atom = item.find('atom:link[@rel="alternate"]', ns)
            if link_atom is not None:
                link_el = type('obj', (object,), {'text': link_atom.get('href')})()
        if desc_el is None:
            desc_el = item.find('atom:content', ns)
        if pubdate_el is None:
            pubdate_el = item.find('atom:published', ns)
            if pubdate_el is None:
                pubdate_el = item.find('atom:updated', ns)

        title = title_el.text if title_el is not None and title_el.text else ''
        link = link_el.text if link_el is not None and link_el.text else ''
        desc = desc_el.text if desc_el is not None and desc_el.text else ''
        pubdate = pubdate_el.text if pubdate_el is not None and pubdate_el.text else ''

        # Tweet-Text aus Title oder Description
        text = title or desc
        if not text:
            return None

        # HTML Tags entfernen
        text = re.sub(r'<[^>]+>', ' ', text)
        text = htmlmod.unescape(text).strip()
        # Nitter fuegt oft "RT by @..." oder "R to @..." prefix hinzu
        text = re.sub(r'^(?:RT|R to) by @\w+:\s*', '', text)

        # Tweet-ID aus URL extrahieren
        tweet_id = ''
        if link:
            m = re.search(r'/status/(\d+)', link)
            if m:
                tweet_id = m.group(1)

        # Published datetime
        published = ''
        if pubdate:
            try:
                published = dateparser.parse(pubdate).isoformat()
            except (ValueError, TypeError):
                pass

        return {
            'text': text,
            'id_str': tweet_id,
            'created_at': published,
            'lang': 'de',
            'user': {
                'screen_name': account,
                'name': account,
                'profile_image_url_https': '',
            },
            'url': link,
        }

    # === Strategie 2: RSSHub ===

    def _fetch_rsshub(self, account):
        """Hole Tweets via RSSHub Instanzen."""
        for instance in RSSHUB_INSTANCES:
            try:
                url = '{}/twitter/user/{}'.format(instance, account)
                resp = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                })
                if resp.status_code != 200:
                    continue

                tweets = self._parse_rss_feed(resp.text, account)
                if tweets:
                    return tweets
            except Exception:
                continue
        return []

    # === Strategie 3: Twitter Syndication API (Legacy) ===

    def _fetch_syndication(self, account):
        """Hole Tweets via Twitter Syndication API (oft blockiert)."""
        url = "https://syndication.twitter.com/srv/timeline-profile/screen-name/%s" % account
        try:
            resp = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            })
            if resp.status_code != 200:
                return []

            match = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                resp.text, re.DOTALL
            )
            if not match:
                return []

            data = json.loads(match.group(1))
            entries = (data.get('props', {})
                       .get('pageProps', {})
                       .get('timeline', {})
                       .get('entries', []))

            tweets = []
            for entry in entries:
                tweet = entry.get('content', {}).get('tweet', {})
                if tweet and tweet.get('id_str'):
                    tweets.append(tweet)
            return tweets
        except Exception:
            return []

    # === Strategie 4: Google-Suche nach Tweets ===

    def _fetch_via_google(self, account):
        """Suche nach Tweets eines Accounts via Google RSS."""
        try:
            query = 'site:x.com/{} OR site:twitter.com/{}'.format(account, account)
            url = 'https://news.google.com/rss/search?q={}&hl=de&gl=DE&ceid=DE:de'.format(
                requests.utils.quote(query)
            )
            resp = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            })
            if resp.status_code != 200:
                return []

            tweets = []
            try:
                root = ET.fromstring(resp.text)
            except ET.ParseError:
                return []

            items = root.findall('.//item')
            for item in items[:10]:
                title_el = item.find('title')
                link_el = item.find('link')
                pubdate_el = item.find('pubDate')

                title = title_el.text if title_el is not None else ''
                link = link_el.text if link_el is not None else ''
                pubdate = pubdate_el.text if pubdate_el is not None else ''

                if not link or ('x.com' not in link and 'twitter.com' not in link):
                    continue

                tweet_id = ''
                m = re.search(r'/status/(\d+)', link)
                if m:
                    tweet_id = m.group(1)

                published = ''
                if pubdate:
                    try:
                        published = dateparser.parse(pubdate).isoformat()
                    except (ValueError, TypeError):
                        pass

                tweets.append({
                    'text': htmlmod.unescape(title),
                    'id_str': tweet_id,
                    'created_at': published,
                    'lang': 'de',
                    'user': {
                        'screen_name': account,
                        'name': account,
                        'profile_image_url_https': '',
                    },
                    'url': link,
                })

            return tweets
        except Exception:
            return []

    # === Hilfsfunktionen ===

    def _is_relevant(self, tweet, search_term):
        """Pruefe ob ein Tweet relevant fuer Giga Berlin ist."""
        text = (tweet.get('full_text', '') or tweet.get('text', '')).lower()
        # Pruefe Suchbegriff
        if search_term and search_term.lower().strip('"') in text:
            return True
        # Pruefe allgemeine Relevanz-Keywords
        return any(kw in text for kw in RELEVANCE_KEYWORDS)

    def _tweet_to_article(self, tweet, fallback_account, search_term, lang=None):
        """Konvertiere Tweet-Daten zu CollectedArticle."""
        user = tweet.get('user', {})
        handle = user.get('screen_name', fallback_account)
        name = user.get('name', handle)
        avatar = user.get('profile_image_url_https', '')
        if avatar:
            avatar = avatar.replace('_normal.', '_200x200.')

        text = tweet.get('full_text', '') or tweet.get('text', '')
        if not text:
            return None

        tweet_id = tweet.get('id_str', '')
        # URL direkt aus Tweet-Daten oder konstruieren
        tweet_url = tweet.get('url', '')
        if not tweet_url and tweet_id:
            tweet_url = 'https://x.com/{}/status/{}'.format(handle, tweet_id)
        elif not tweet_url:
            return None

        published = tweet.get('created_at', '')
        published_iso = None
        if published:
            # Schon ISO format?
            if 'T' in published:
                published_iso = published
            else:
                try:
                    published_iso = dateparser.parse(published).isoformat()
                except (ValueError, TypeError):
                    pass

        tweet_lang = tweet.get('lang', lang or 'de')
        if tweet_lang not in ('de', 'en', 'pl'):
            tweet_lang = lang or 'de'

        return CollectedArticle(
            url=tweet_url,
            title=self._clean_text(text),
            snippet=self._clean_text(text),
            source_name='@{}|{}|{}'.format(handle, name, avatar),
            source_type='twitter',
            search_term=search_term,
            published_at=published_iso,
            image_url=avatar,
            language=tweet_lang
        )

    def _clean_text(self, text):
        """Bereinige Tweet-Text."""
        if not text:
            return ''
        text = htmlmod.unescape(text)
        text = re.sub(r'https://t\.co/\w+', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
