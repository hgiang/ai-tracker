from app.adapters.arxiv import ArxivAdapter
from app.adapters.base import BaseAdapter
from app.adapters.bluesky import BlueskyAdapter
from app.adapters.github import GitHubAdapter
from app.adapters.hackernews import HackerNewsAdapter
from app.adapters.hf_papers import HFPapersAdapter
from app.adapters.polymarket import PolymarketAdapter
from app.adapters.reddit import RedditAdapter
from app.adapters.rss import RSSAdapter
from app.adapters.x import XAdapter

ADAPTER_MAP: dict[str, type[BaseAdapter]] = {
    "hackernews": HackerNewsAdapter,
    "reddit": RedditAdapter,
    "arxiv": ArxivAdapter,
    "github": GitHubAdapter,
    "rss": RSSAdapter,
    "x": XAdapter,
    "bluesky": BlueskyAdapter,
    "polymarket": PolymarketAdapter,
    "hf_papers": HFPapersAdapter,
}


def get_adapter(adapter_type: str, source_url: str, **kwargs: str) -> BaseAdapter:
    cls = ADAPTER_MAP.get(adapter_type)
    if cls is None:
        raise ValueError(f"Unknown adapter type: {adapter_type}")
    return cls(source_url=source_url, **kwargs)


DEFAULT_SOURCES = [
    {"name": "Hacker News", "slug": "hackernews", "adapter_type": "hackernews", "url": "https://news.ycombinator.com"},
    {"name": "Reddit ML", "slug": "reddit-ml", "adapter_type": "rss", "url": "https://www.reddit.com/r/MachineLearning/hot.rss"},
    {"name": "Reddit LocalLLaMA", "slug": "reddit-localllama", "adapter_type": "rss", "url": "https://www.reddit.com/r/LocalLLaMA/hot.rss"},
    {"name": "Reddit Artificial", "slug": "reddit-artificial", "adapter_type": "rss", "url": "https://www.reddit.com/r/artificial/hot.rss"},
    {"name": "Reddit ChatGPT", "slug": "reddit-chatgpt", "adapter_type": "rss", "url": "https://www.reddit.com/r/ChatGPT/hot.rss"},
    {"name": "Reddit OpenAI", "slug": "reddit-openai", "adapter_type": "rss", "url": "https://www.reddit.com/r/OpenAI/hot.rss"},
    {"name": "Reddit Deep Learning", "slug": "reddit-deeplearning", "adapter_type": "rss", "url": "https://www.reddit.com/r/deeplearning/hot.rss"},
    {"name": "Reddit LanguageTechnology", "slug": "reddit-languagetechnology", "adapter_type": "rss", "url": "https://www.reddit.com/r/LanguageTechnology/hot.rss"},
    {"name": "Reddit ClaudeAI", "slug": "reddit-claudeai", "adapter_type": "rss", "url": "https://www.reddit.com/r/ClaudeAI/hot.rss"},
    {"name": "arXiv cs.AI", "slug": "arxiv-csai", "adapter_type": "arxiv", "url": "https://arxiv.org", "config": {"category": "cs.AI"}},
    {"name": "arXiv cs.CL", "slug": "arxiv-cscl", "adapter_type": "arxiv", "url": "https://arxiv.org", "config": {"category": "cs.CL"}},
    {"name": "arXiv cs.MA", "slug": "arxiv-csma", "adapter_type": "arxiv", "url": "https://arxiv.org", "config": {"category": "cs.MA"}},
    {"name": "X - AI Leaders", "slug": "x-ai-leaders", "adapter_type": "x", "url": "https://x.com"},
    {"name": "Bluesky - AI Voices", "slug": "bluesky-ai", "adapter_type": "bluesky", "url": "https://bsky.app"},
    {"name": "HF Daily Papers", "slug": "hf-papers", "adapter_type": "hf_papers", "url": "https://huggingface.co/papers"},
    {"name": "GitHub Trending AI", "slug": "github-ai", "adapter_type": "github", "url": "https://github.com"},
    {"name": "OpenAI Blog", "slug": "openai-blog", "adapter_type": "rss", "url": "https://openai.com/news/rss.xml"},
    {"name": "Google AI Blog", "slug": "google-ai-blog", "adapter_type": "rss", "url": "https://blog.google/innovation-and-ai/technology/ai/rss/"},
    {"name": "Hugging Face Blog", "slug": "hf-blog", "adapter_type": "rss", "url": "https://huggingface.co/blog/feed.xml"},
    # Podcasts
    {"name": "TWIML AI Podcast", "slug": "podcast-twiml", "adapter_type": "rss", "url": "https://twimlai.com/feed", "config": {"content_type": "podcast"}},
    {"name": "Practical AI Podcast", "slug": "podcast-practical-ai", "adapter_type": "rss", "url": "https://changelog.com/practicalai/feed", "config": {"content_type": "podcast"}},
    {"name": "The AI Breakdown", "slug": "podcast-ai-breakdown", "adapter_type": "rss", "url": "https://feeds.libsyn.com/468519/rss", "config": {"content_type": "podcast"}},
    {"name": "This Day in AI", "slug": "podcast-this-day-in-ai", "adapter_type": "rss", "url": "https://feeds.transistor.fm/this-day-in-ai", "config": {"content_type": "podcast"}},
    {"name": "Eye On A.I.", "slug": "podcast-eye-on-ai", "adapter_type": "rss", "url": "https://aneyeonai.libsyn.com/rss", "config": {"content_type": "podcast"}},
    {"name": "The Gradient Podcast", "slug": "podcast-gradient", "adapter_type": "rss", "url": "https://api.substack.com/feed/podcast/265424/s/1354.rss", "config": {"content_type": "podcast"}},
    {"name": "Real Python Podcast", "slug": "podcast-real-python", "adapter_type": "rss", "url": "https://realpython.com/podcasts/rpp/feed", "config": {"content_type": "podcast"}},
    # Videos (YouTube)
    {"name": "Two Minute Papers", "slug": "yt-two-minute-papers", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCbfYPyITQ-7l4upoX8nvctg", "config": {"content_type": "video"}},
    {"name": "Yannic Kilcher", "slug": "yt-yannic-kilcher", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCZHmQk67mSJgfCCTn7xBfew", "config": {"content_type": "video"}},
    {"name": "AI Explained", "slug": "yt-ai-explained", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCNJ1Ymd5yFuUPtn21xtRbbw", "config": {"content_type": "video"}},
    {"name": "Machine Learning Street Talk", "slug": "yt-mlst", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCMLtBahI5DMrt0NPvDSoIRQ", "config": {"content_type": "video"}},
    {"name": "DeepMind", "slug": "yt-deepmind", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCP7jMXSY2xbc3KCAE0MHQ-A", "config": {"content_type": "video"}},
    {"name": "Weights & Biases", "slug": "yt-wandb", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCBp3w4DCEC64FZr4k9ROxig", "config": {"content_type": "video"}},
    {"name": "Aleksa Gordić - The AI Epiphany", "slug": "yt-aleksa-gordic", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCj8shE7aIn4Yawwbo2FceCQ", "config": {"content_type": "video"}},
    {"name": "Vizuara", "slug": "yt-vizuara", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCdEov4L0bpJ_h6W3sJxkfUA", "config": {"content_type": "video"}},
    {"name": "AI Engineer", "slug": "yt-ai-engineer", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCLKPca3kwwd-B59HNr-_lvA", "config": {"content_type": "video"}},
    {"name": "Data Science Dojo", "slug": "yt-datasciencedojo", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCzL_0nIe8B4-7ShhVPfJkgw", "config": {"content_type": "video"}},
    {"name": "Vanishing Gradients", "slug": "yt-vanishing-gradients", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC_NafIo-Ku2loOLrzm45ABA", "config": {"content_type": "video"}},
    {"name": "Hugging Face", "slug": "yt-huggingface", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCHlNU7kIZhRgSbhHvFoy72w", "config": {"content_type": "video"}},
    {"name": "Neuriton", "slug": "yt-neuriton", "adapter_type": "rss", "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCn1rhibEsaavZUTcWN5xzmg", "config": {"content_type": "video"}},
]
