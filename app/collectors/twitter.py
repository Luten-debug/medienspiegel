"""Twitter/X Collector - holt echte Tweets via Twitter Syndication API."""

import re
import json
import html as htmlmod
import requests
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
    'giga berlin', 'gigafactory', 'gruenheide', 'grünheide', 'gruenheide',
    'giga factory', 'tesla berlin', 'tesla germany', 'tesla deutschland',
    'tesla brandenburg', 'gigaberlin', 'giga-berlin',
    'betriebsrat', 'ig metall', 'works council',
    'robotaxi', 'cybercab', 'model y',
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
        """Sammle Tweets von bekannten Accounts via Syndication API."""
        twitter_config = self.config.get('twitter', {})
        accounts = twitter_config.get('accounts', DEFAULT_ACCOUNTS)
        max_tweets = twitter_config.get('max_tweets', 20)

        articles = []
        for account in accounts:
            try:
                tweets = self._fetch_account_tweets(account)
                for tweet in tweets:
                    if self._is_relevant(tweet, search_term):
                        article = self._tweet_to_article(tweet, search_term, lang)
                        if article:
                            articles.append(article)
            except Exception:
                continue

            if len(articles) >= max_tweets:
                break

        return articles[:max_tweets]

    def _fetch_account_tweets(self, account):
        """Hole Tweets eines Accounts via Twitter Syndication API."""
        url = "https://syndication.twitter.com/srv/timeline-profile/screen-name/%s" % account
        resp = requests.get(url, timeout=15, headers={
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

        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            return []

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

    def _is_relevant(self, tweet, search_term):
        """Pruefe ob ein Tweet relevant fuer Giga Berlin ist."""
        text = (tweet.get('full_text', '') or tweet.get('text', '')).lower()
        # Pruefe Suchbegriff
        if search_term and search_term.lower().strip('"') in text:
            return True
        # Pruefe allgemeine Relevanz-Keywords
        return any(kw in text for kw in RELEVANCE_KEYWORDS)

    def _tweet_to_article(self, tweet, search_term, lang=None):
        """Konvertiere Tweet-Daten zu CollectedArticle."""
        user = tweet.get('user', {})
        handle = user.get('screen_name', '')
        name = user.get('name', handle)
        avatar = user.get('profile_image_url_https', '')
        # Hoehere Aufloesung: _normal.jpg -> _200x200.jpg
        if avatar:
            avatar = avatar.replace('_normal.', '_200x200.')

        text = tweet.get('full_text', '') or tweet.get('text', '')
        tweet_id = tweet.get('id_str', '')
        tweet_url = 'https://x.com/%s/status/%s' % (handle, tweet_id)

        published = tweet.get('created_at', '')
        published_iso = None
        if published:
            try:
                published_iso = dateparser.parse(published).isoformat()
            except (ValueError, TypeError):
                pass

        # Sprache aus dem Tweet
        tweet_lang = tweet.get('lang', lang or 'de')
        if tweet_lang not in ('de', 'en', 'pl'):
            tweet_lang = lang or 'de'

        return CollectedArticle(
            url=tweet_url,
            title=self._clean_text(text),
            snippet=self._clean_text(text),
            source_name='@%s|%s|%s' % (handle, name, avatar),
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
        # t.co Links durch [Link] ersetzen
        text = re.sub(r'https://t\.co/\w+', '', text)
        return text.strip()
