"""Data schemas for last30days skill."""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


@dataclass
class Engagement:
    """Engagement metrics."""
    # Reddit fields
    score: Optional[int] = None
    num_comments: Optional[int] = None
    upvote_ratio: Optional[float] = None

    # X fields
    likes: Optional[int] = None
    reposts: Optional[int] = None
    replies: Optional[int] = None
    quotes: Optional[int] = None

    # Hacker News fields
    points: Optional[int] = None
    comments: Optional[int] = None  # shared by HN + GitHub (comment count)

    # GitHub fields
    reactions: Optional[int] = None

    # Polymarket fields (real-money signal)
    volume: Optional[float] = None
    liquidity: Optional[float] = None
    odds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {}
        if self.score is not None:
            d['score'] = self.score
        if self.num_comments is not None:
            d['num_comments'] = self.num_comments
        if self.upvote_ratio is not None:
            d['upvote_ratio'] = self.upvote_ratio
        if self.likes is not None:
            d['likes'] = self.likes
        if self.reposts is not None:
            d['reposts'] = self.reposts
        if self.replies is not None:
            d['replies'] = self.replies
        if self.quotes is not None:
            d['quotes'] = self.quotes
        if self.points is not None:
            d['points'] = self.points
        if self.comments is not None:
            d['comments'] = self.comments
        if self.reactions is not None:
            d['reactions'] = self.reactions
        if self.volume is not None:
            d['volume'] = self.volume
        if self.liquidity is not None:
            d['liquidity'] = self.liquidity
        if self.odds is not None:
            d['odds'] = self.odds
        return d if d else None


@dataclass
class Comment:
    """Reddit comment."""
    score: int
    date: Optional[str]
    author: str
    excerpt: str
    url: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            'score': self.score,
            'date': self.date,
            'author': self.author,
            'excerpt': self.excerpt,
            'url': self.url,
        }


@dataclass
class SubScores:
    """Component scores."""
    relevance: int = 0
    recency: int = 0
    engagement: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            'relevance': self.relevance,
            'recency': self.recency,
            'engagement': self.engagement,
        }


@dataclass
class RedditItem:
    """Normalized Reddit item."""
    id: str
    title: str
    url: str
    subreddit: str
    date: Optional[str] = None
    date_confidence: str = "low"
    engagement: Optional[Engagement] = None
    top_comments: List[Comment] = field(default_factory=list)
    comment_insights: List[str] = field(default_factory=list)
    relevance: float = 0.5
    why_relevant: str = ""
    subs: SubScores = field(default_factory=SubScores)
    score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'subreddit': self.subreddit,
            'date': self.date,
            'date_confidence': self.date_confidence,
            'engagement': self.engagement.to_dict() if self.engagement else None,
            'top_comments': [c.to_dict() for c in self.top_comments],
            'comment_insights': self.comment_insights,
            'relevance': self.relevance,
            'why_relevant': self.why_relevant,
            'subs': self.subs.to_dict(),
            'score': self.score,
        }


@dataclass
class XItem:
    """Normalized X item."""
    id: str
    text: str
    url: str
    author_handle: str
    date: Optional[str] = None
    date_confidence: str = "low"
    engagement: Optional[Engagement] = None
    relevance: float = 0.5
    why_relevant: str = ""
    subs: SubScores = field(default_factory=SubScores)
    score: int = 0
    # Thread enrichment fields
    thread_replies: List[str] = field(default_factory=list)
    thread_insight: str = ""
    is_thread_head: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = {
            'id': self.id,
            'text': self.text,
            'url': self.url,
            'author_handle': self.author_handle,
            'date': self.date,
            'date_confidence': self.date_confidence,
            'engagement': self.engagement.to_dict() if self.engagement else None,
            'relevance': self.relevance,
            'why_relevant': self.why_relevant,
            'subs': self.subs.to_dict(),
            'score': self.score,
        }
        if self.thread_replies:
            d['thread_replies'] = self.thread_replies
        if self.thread_insight:
            d['thread_insight'] = self.thread_insight
        if self.is_thread_head:
            d['is_thread_head'] = self.is_thread_head
        return d


@dataclass
class WebSearchItem:
    """Normalized web search item (no engagement metrics)."""
    id: str
    title: str
    url: str
    source_domain: str  # e.g., "medium.com", "github.com"
    snippet: str
    date: Optional[str] = None
    date_confidence: str = "low"
    relevance: float = 0.5
    why_relevant: str = ""
    subs: SubScores = field(default_factory=SubScores)
    score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'source_domain': self.source_domain,
            'snippet': self.snippet,
            'date': self.date,
            'date_confidence': self.date_confidence,
            'relevance': self.relevance,
            'why_relevant': self.why_relevant,
            'subs': self.subs.to_dict(),
            'score': self.score,
        }


@dataclass
class HackerNewsItem:
    """Normalized Hacker News story."""
    id: str
    title: str
    url: str  # article URL (may be empty for Ask/Show HN text posts)
    hn_url: str  # news.ycombinator.com discussion URL
    author: str = ""
    date: Optional[str] = None
    date_confidence: str = "low"
    engagement: Optional[Engagement] = None
    top_comments: List[Dict[str, Any]] = field(default_factory=list)
    comment_insights: List[str] = field(default_factory=list)
    relevance: float = 0.5
    why_relevant: str = ""
    subs: SubScores = field(default_factory=SubScores)
    score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'hn_url': self.hn_url,
            'author': self.author,
            'date': self.date,
            'date_confidence': self.date_confidence,
            'engagement': self.engagement.to_dict() if self.engagement else None,
            'top_comments': self.top_comments,
            'comment_insights': self.comment_insights,
            'relevance': self.relevance,
            'why_relevant': self.why_relevant,
            'subs': self.subs.to_dict(),
            'score': self.score,
        }


@dataclass
class GitHubItem:
    """Normalized GitHub issue/PR."""
    id: str
    title: str
    url: str
    author: str = ""
    container: str = ""  # owner/repo
    snippet: str = ""
    date: Optional[str] = None
    date_confidence: str = "low"
    engagement: Optional[Engagement] = None
    is_pr: bool = False
    state: str = ""
    labels: List[str] = field(default_factory=list)
    top_comments: List[Dict[str, Any]] = field(default_factory=list)
    relevance: float = 0.5
    why_relevant: str = ""
    subs: SubScores = field(default_factory=SubScores)
    score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'author': self.author,
            'container': self.container,
            'snippet': self.snippet,
            'date': self.date,
            'date_confidence': self.date_confidence,
            'engagement': self.engagement.to_dict() if self.engagement else None,
            'is_pr': self.is_pr,
            'state': self.state,
            'labels': self.labels,
            'top_comments': self.top_comments,
            'relevance': self.relevance,
            'why_relevant': self.why_relevant,
            'subs': self.subs.to_dict(),
            'score': self.score,
        }


@dataclass
class PolymarketItem:
    """Normalized Polymarket prediction-market event."""
    id: str
    title: str
    url: str
    question: str = ""
    outcome_prices: List[Any] = field(default_factory=list)  # [(name, price), ...]
    outcomes_remaining: int = 0
    price_movement: Optional[str] = None
    end_date: Optional[str] = None
    date: Optional[str] = None
    date_confidence: str = "low"
    engagement: Optional[Engagement] = None
    relevance: float = 0.5
    why_relevant: str = ""
    subs: SubScores = field(default_factory=SubScores)
    score: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'question': self.question,
            'outcome_prices': [list(p) for p in self.outcome_prices],
            'outcomes_remaining': self.outcomes_remaining,
            'price_movement': self.price_movement,
            'end_date': self.end_date,
            'date': self.date,
            'date_confidence': self.date_confidence,
            'engagement': self.engagement.to_dict() if self.engagement else None,
            'relevance': self.relevance,
            'why_relevant': self.why_relevant,
            'subs': self.subs.to_dict(),
            'score': self.score,
        }


@dataclass
class Report:
    """Full research report."""
    topic: str
    range_from: str
    range_to: str
    generated_at: str
    mode: str  # 'reddit-only', 'x-only', 'both', 'web-only', etc.
    openai_model_used: Optional[str] = None
    xai_model_used: Optional[str] = None
    reddit: List[RedditItem] = field(default_factory=list)
    x: List[XItem] = field(default_factory=list)
    web: List[WebSearchItem] = field(default_factory=list)
    hackernews: List[HackerNewsItem] = field(default_factory=list)
    github: List[GitHubItem] = field(default_factory=list)
    polymarket: List[PolymarketItem] = field(default_factory=list)
    best_practices: List[str] = field(default_factory=list)
    prompt_pack: List[str] = field(default_factory=list)
    context_snippet_md: str = ""
    # Status tracking
    reddit_error: Optional[str] = None
    x_error: Optional[str] = None
    web_error: Optional[str] = None
    hackernews_error: Optional[str] = None
    github_error: Optional[str] = None
    polymarket_error: Optional[str] = None
    # Cache info
    from_cache: bool = False
    cache_age_hours: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            'topic': self.topic,
            'range': {
                'from': self.range_from,
                'to': self.range_to,
            },
            'generated_at': self.generated_at,
            'mode': self.mode,
            'openai_model_used': self.openai_model_used,
            'xai_model_used': self.xai_model_used,
            'reddit': [r.to_dict() for r in self.reddit],
            'x': [x.to_dict() for x in self.x],
            'web': [w.to_dict() for w in self.web],
            'hackernews': [h.to_dict() for h in self.hackernews],
            'github': [g.to_dict() for g in self.github],
            'polymarket': [p.to_dict() for p in self.polymarket],
            'best_practices': self.best_practices,
            'prompt_pack': self.prompt_pack,
            'context_snippet_md': self.context_snippet_md,
        }
        if self.reddit_error:
            d['reddit_error'] = self.reddit_error
        if self.x_error:
            d['x_error'] = self.x_error
        if self.web_error:
            d['web_error'] = self.web_error
        if self.hackernews_error:
            d['hackernews_error'] = self.hackernews_error
        if self.github_error:
            d['github_error'] = self.github_error
        if self.polymarket_error:
            d['polymarket_error'] = self.polymarket_error
        if self.from_cache:
            d['from_cache'] = self.from_cache
        if self.cache_age_hours is not None:
            d['cache_age_hours'] = self.cache_age_hours
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Report":
        """Create Report from serialized dict (handles cache format)."""
        # Handle range field conversion
        range_data = data.get('range', {})
        range_from = range_data.get('from', data.get('range_from', ''))
        range_to = range_data.get('to', data.get('range_to', ''))

        # Reconstruct Reddit items
        reddit_items = []
        for r in data.get('reddit', []):
            eng = None
            if r.get('engagement'):
                eng = Engagement(**r['engagement'])
            comments = [Comment(**c) for c in r.get('top_comments', [])]
            subs = SubScores(**r.get('subs', {})) if r.get('subs') else SubScores()
            reddit_items.append(RedditItem(
                id=r['id'],
                title=r['title'],
                url=r['url'],
                subreddit=r['subreddit'],
                date=r.get('date'),
                date_confidence=r.get('date_confidence', 'low'),
                engagement=eng,
                top_comments=comments,
                comment_insights=r.get('comment_insights', []),
                relevance=r.get('relevance', 0.5),
                why_relevant=r.get('why_relevant', ''),
                subs=subs,
                score=r.get('score', 0),
            ))

        # Reconstruct X items
        x_items = []
        for x in data.get('x', []):
            eng = None
            if x.get('engagement'):
                eng = Engagement(**x['engagement'])
            subs = SubScores(**x.get('subs', {})) if x.get('subs') else SubScores()
            x_items.append(XItem(
                id=x['id'],
                text=x['text'],
                url=x['url'],
                author_handle=x['author_handle'],
                date=x.get('date'),
                date_confidence=x.get('date_confidence', 'low'),
                engagement=eng,
                relevance=x.get('relevance', 0.5),
                why_relevant=x.get('why_relevant', ''),
                subs=subs,
                score=x.get('score', 0),
                thread_replies=x.get('thread_replies', []),
                thread_insight=x.get('thread_insight', ''),
                is_thread_head=x.get('is_thread_head', False),
            ))

        # Reconstruct Web items
        web_items = []
        for w in data.get('web', []):
            subs = SubScores(**w.get('subs', {})) if w.get('subs') else SubScores()
            web_items.append(WebSearchItem(
                id=w['id'],
                title=w['title'],
                url=w['url'],
                source_domain=w.get('source_domain', ''),
                snippet=w.get('snippet', ''),
                date=w.get('date'),
                date_confidence=w.get('date_confidence', 'low'),
                relevance=w.get('relevance', 0.5),
                why_relevant=w.get('why_relevant', ''),
                subs=subs,
                score=w.get('score', 0),
            ))

        # Reconstruct Hacker News items
        hn_items = []
        for h in data.get('hackernews', []):
            eng = None
            if h.get('engagement'):
                eng = Engagement(**h['engagement'])
            subs = SubScores(**h.get('subs', {})) if h.get('subs') else SubScores()
            hn_items.append(HackerNewsItem(
                id=h['id'],
                title=h['title'],
                url=h.get('url', ''),
                hn_url=h.get('hn_url', ''),
                author=h.get('author', ''),
                date=h.get('date'),
                date_confidence=h.get('date_confidence', 'low'),
                engagement=eng,
                top_comments=h.get('top_comments', []),
                comment_insights=h.get('comment_insights', []),
                relevance=h.get('relevance', 0.5),
                why_relevant=h.get('why_relevant', ''),
                subs=subs,
                score=h.get('score', 0),
            ))

        # Reconstruct GitHub items
        github_items = []
        for g in data.get('github', []):
            eng = None
            if g.get('engagement'):
                eng = Engagement(**g['engagement'])
            subs = SubScores(**g.get('subs', {})) if g.get('subs') else SubScores()
            github_items.append(GitHubItem(
                id=g['id'],
                title=g['title'],
                url=g.get('url', ''),
                author=g.get('author', ''),
                container=g.get('container', ''),
                snippet=g.get('snippet', ''),
                date=g.get('date'),
                date_confidence=g.get('date_confidence', 'low'),
                engagement=eng,
                is_pr=g.get('is_pr', False),
                state=g.get('state', ''),
                labels=g.get('labels', []),
                top_comments=g.get('top_comments', []),
                relevance=g.get('relevance', 0.5),
                why_relevant=g.get('why_relevant', ''),
                subs=subs,
                score=g.get('score', 0),
            ))

        # Reconstruct Polymarket items
        polymarket_items = []
        for p in data.get('polymarket', []):
            eng = None
            if p.get('engagement'):
                eng = Engagement(**p['engagement'])
            subs = SubScores(**p.get('subs', {})) if p.get('subs') else SubScores()
            polymarket_items.append(PolymarketItem(
                id=p['id'],
                title=p['title'],
                url=p.get('url', ''),
                question=p.get('question', ''),
                outcome_prices=[tuple(op) for op in p.get('outcome_prices', [])],
                outcomes_remaining=p.get('outcomes_remaining', 0),
                price_movement=p.get('price_movement'),
                end_date=p.get('end_date'),
                date=p.get('date'),
                date_confidence=p.get('date_confidence', 'low'),
                engagement=eng,
                relevance=p.get('relevance', 0.5),
                why_relevant=p.get('why_relevant', ''),
                subs=subs,
                score=p.get('score', 0),
            ))

        return cls(
            topic=data['topic'],
            range_from=range_from,
            range_to=range_to,
            generated_at=data['generated_at'],
            mode=data['mode'],
            openai_model_used=data.get('openai_model_used'),
            xai_model_used=data.get('xai_model_used'),
            reddit=reddit_items,
            x=x_items,
            web=web_items,
            hackernews=hn_items,
            github=github_items,
            polymarket=polymarket_items,
            best_practices=data.get('best_practices', []),
            prompt_pack=data.get('prompt_pack', []),
            context_snippet_md=data.get('context_snippet_md', ''),
            reddit_error=data.get('reddit_error'),
            x_error=data.get('x_error'),
            web_error=data.get('web_error'),
            hackernews_error=data.get('hackernews_error'),
            github_error=data.get('github_error'),
            polymarket_error=data.get('polymarket_error'),
            from_cache=data.get('from_cache', False),
            cache_age_hours=data.get('cache_age_hours'),
        )


def create_report(
    topic: str,
    from_date: str,
    to_date: str,
    mode: str,
    openai_model: Optional[str] = None,
    xai_model: Optional[str] = None,
) -> Report:
    """Create a new report with metadata."""
    return Report(
        topic=topic,
        range_from=from_date,
        range_to=to_date,
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        openai_model_used=openai_model,
        xai_model_used=xai_model,
    )
