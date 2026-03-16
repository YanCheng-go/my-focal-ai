"""Shared constants and pure resolvers for URL → source field extraction.

Used by both src/ainews/sources/url_resolver.py (async, FastAPI) and
api/resolve_url.py (sync, Vercel serverless).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# ── Host sets ──────────────────────────────────────────────────────

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
TWITTER_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}
ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}
XHS_HOSTS = {"xiaohongshu.com", "www.xiaohongshu.com", "xhslink.com"}
LUMA_HOSTS = {"lu.ma", "www.lu.ma"}
RSSHUB_HOSTS = {"rsshub.app", "www.rsshub.app"}

# Maps normalized URL paths → RSSHub route.
# RSSHub is preferred over Olshansk (self-hosted, real-time).
# AUTO-GENERATED — do not edit by hand. Run scripts/sync_rsshub_routes.py to update.
# --- BEGIN RSSHUB_URL_MAP (auto-generated) ---
RSSHUB_URL_MAP: dict[str, str] = {
    "0daily.com/activityPage": "/odaily/activity",  # noqa: E501
    "0daily.com/newsflash": "/odaily/newsflash",  # noqa: E501
    "51cto.com": "/51cto/index/recommend",  # noqa: E501
    "acg17.com/post": "/acg17/post/all",  # noqa: E501
    "admission.nju.edu.cn/tzgg/index.html": "/nju/admission",  # noqa: E501
    "admission.pku.edu.cn/zsxx/sszs/index.htm": "/pku/admission/sszs",  # noqa: E501
    "aflcio.org": "/aflcio/blog",  # noqa: E501
    "agemys.org/update": "/agefans/update",  # noqa: E501
    "agirls.aotter.net": "/agirls/topic_list",  # noqa: E501
    "agorahub.github.io/pen0": "/agora0/pen0",  # noqa: E501
    "ai-bot.cn/daily-ai-news": "/ai-bot/daily-ai-news",  # noqa: E501
    "ai.gxmzu.edu.cn/index/tzgg.htm": "/gxmzu/aitzgg",  # noqa: E501
    "ai.meta.com/blog": "/meta/ai/blog",  # noqa: E501
    "ai.ucas.ac.cn/index.php/zh-cn/tzgg": "/ucas/ai",  # noqa: E501
    "alwayscontrol.com.cn": "/alwayscontrol/news",  # noqa: E501
    "amz123.com/kx": "/amz123/kx",  # noqa: E501
    "anytxt.net": "/anytxt/release-notes",  # noqa: E501
    "apod.nasa.govundefined": "/nasa/apod",  # noqa: E501
    "app.so/xianmian": "/appstore/xianmian",  # noqa: E501
    "asiafruitchina.net": "/asiafruitchina/news",  # noqa: E501
    "asus.com/campaign/GPU-Tweak-III/*": "/asus/gpu-tweak",  # noqa: E501
    "auto.uestc.edu.cn": "/uestc/auto",  # noqa: E501
    "backlinko.com/blog": "/backlinko/blog",  # noqa: E501
    "bandcamp.com/live_schedule": "/bandcamp/live",  # noqa: E501
    "bbcnewslabs.co.uk": "/bbcnewslabs/news",  # noqa: E501
    "bellroy.com/collection/new-releases": "/bellroy/new-releases",  # noqa: E501
    "bfl.ai/announcements": "/bfl/announcements",  # noqa: E501
    "biddingoffice.sustech.edu.cn": "/sustech/bidding",  # noqa: E501
    "bigquant.com": "/bigquant/collections",  # noqa: E501
    "bioone.org": "/bioone/featured",  # noqa: E501
    "bitmovin.com/blog": "/bitmovin/blog",  # noqa: E501
    "bjp.org.cn/APOD/today.shtml": "/bjp/apod",  # noqa: E501
    "bksy.tongji.edu.cn": "/tongji/bks",  # noqa: E501
    "bluestacks.com/hc/en-us/articles/360056960211-Release-Notes-BlueStacks-5": "/bluestacks/release/5",  # noqa: E501
    "bmkg.go.id": "/bmkg/news",  # noqa: E501
    "brave.com/latest": "/brave/latest",  # noqa: E501
    "btbtla.com/tt/gxlist.html": "/btbtla/gxlist",  # noqa: E501
    "buct.edu.cn": "/buct/cist",  # noqa: E501
    "bupt.edu.cn": "/bupt/rczp",  # noqa: E501
    "caareviews.org/reviews/book": "/caareviews/book",  # noqa: E501
    "caareviews.org/reviews/essay": "/caareviews/essay",  # noqa: E501
    "caareviews.org/reviews/exhibition": "/caareviews/exhibition",  # noqa: E501
    "caixin.com": "/caixin/latest",  # noqa: E501
    "caixinglobal.com/news": "/caixinglobal/latest",  # noqa: E501
    "career.csu.edu.cn/campus/index/category/1": "/csu/career",  # noqa: E501
    "ccnu.91wllm.com/news/index/tag/tzgg": "/ccnu/career",  # noqa: E501
    "censorbib.nymity.ch": "/nymity/censorbib",  # noqa: E501
    "chaincatcher.com/news": "/chaincatcher/news",  # noqa: E501
    "chaping.cn": "/chaping/banner",  # noqa: E501
    "chaping.cn/newsflash": "/chaping/newsflash",  # noqa: E501
    "chinacustoms.gmcmonline.com": "/gmcmonline/chinacustoms",  # noqa: E501
    "civitai.com": "/civitai/models",  # noqa: E501
    "claude.com/blog": "/claude/blog",  # noqa: E501
    "cline.bot/blog": "/cline/blog",  # noqa: E501
    "cls.cn": "/cls/hot",  # noqa: E501
    "cncf.io/reports": "/cncf/reports",  # noqa: E501
    "code.claude.com": "/claude/code/changelog",  # noqa: E501
    "code.visualstudio.com": "/visualstudio/code/blog",  # noqa: E501
    "coindesk.com": "/coindesk/consensus-magazine",  # noqa: E501
    "cookbook.openai.com": "/openai/cookbook",  # noqa: E501
    "coolidge.org/about-us/news-media": "/coolidge/news",  # noqa: E501
    "coolidge.org/film-guide": "/coolidge/film-guide",  # noqa: E501
    "cpuid.com/news.html": "/cpuid/news",  # noqa: E501
    "cqgas.cn": "/cqgas/tqtz",  # noqa: E501
    "cs.ccnu.edu.cn/xwzx/tzgg.htm": "/ccnu/cs",  # noqa: E501
    "cse.sysu.edu.cn": "/sysu/cse",  # noqa: E501
    "cursor.com": "/cursor/changelog",  # noqa: E501
    "cw.com.tw/today": "/cw/today",  # noqa: E501
    "dafls.nju.edu.cn/13167/list.html": "/nju/dafls",  # noqa: E501
    "daily.zhihu.com/*": "/zhihu/daily",  # noqa: E501
    "dealstreetasia.com": "/dealstreetasia/home",  # noqa: E501
    "deepmind.com/blog": "/deepmind/blog",  # noqa: E501
    "delta.io/blog": "/deltaio/blog",  # noqa: E501
    "desktop.webcatalog.io/en/changelog": "/webcatalog/changelog",  # noqa: E501
    "dev.syosetu.com": "/syosetu/dev",  # noqa: E501
    "dev.to": "/dev.to/guides",  # noqa: E501
    "developer.android.com/studio/releases/platform-tools": "/android/platform-tools-releases",  # noqa: E501
    "developer.anitaku.to": "/gogoanimehd/recent-releases",  # noqa: E501
    "developer.apple.com/design/whats-new": "/apple/design",  # noqa: E501
    "devolverdigital.com/blog": "/devolverdigital/blog",  # noqa: E501
    "disinfo.eu": "/disinfo/publications",  # noqa: E501
    "diskanalyzer.com/whats-new": "/diskanalyzer/whats-new",  # noqa: E501
    "dorohedoro.net/news": "/dorohedoro/news",  # noqa: E501
    "download.lineageos.org": "/lineageos/changes",  # noqa: E501
    "due.hitsz.edu.cn": "/hitsz/due/tzgg",  # noqa: E501
    "economist.com/the-world-in-brief": "/economist/espresso",  # noqa: E501
    "eleduck.com/categories/5": "/eleduck/jobs",  # noqa: E501
    "europechinese.blogspot.com": "/europechinese/latest",  # noqa: E501
    "fastbull.com/express-news": "/fastbull/express-news",  # noqa: E501
    "flyert.com": "/flyert/preferential",  # noqa: E501
    "foresightnews.pro": "/foresightnews/article",  # noqa: E501
    "foresightnews.pro/news": "/foresightnews/news",  # noqa: E501
    "fuliba2023.net": "/fuliba/latest",  # noqa: E501
    "furaffinity.net": "/furaffinity/status",  # noqa: E501
    "fx678.com/kx": "/fx678/kx",  # noqa: E501
    "gamekee.com/news": "/gamekee/news",  # noqa: E501
    "github.com/notifications": "/github/notifications",  # noqa: E501
    "gitpod.io/changelog": "/gitpod/changelog",  # noqa: E501
    "gocn.vip": "/gocn/topics",  # noqa: E501
    "graduate.bjfu.edu.cn": "/bjfu/grs",  # noqa: E501
    "grawww.nju.edu.cn/905/list.htm": "/nju/gra",  # noqa: E501
    "grd.bit.edu.cn/zsgz/zsxx/index.htm": "/bit/yjs",  # noqa: E501
    "grist.org": "/grist/featured",  # noqa: E501
    "gs.ccnu.edu.cn/zsgz/ssyjs.htm": "/ccnu/yjs",  # noqa: E501
    "gs.sustech.edu.cn": "/sustech/yjs",  # noqa: E501
    "gs.tongji.edu.cn/tzgg.htm": "/tongji/gs",  # noqa: E501
    "gszs.hust.edu.cn/zsxx/ggtz.htm": "/hust/yjs",  # noqa: E501
    "guancha.cn/GuanChaZheTouTiao": "/guancha/headline",  # noqa: E501
    "guangdiu.com/rank": "/guangdiu/rank",  # noqa: E501
    "guokr.com/scientific": "/guokr/scientific",  # noqa: E501
    "hao6v.com": "/6v123/latestMovies",  # noqa: E501
    "hellobtc.com/news": "/hellobtc/news",  # noqa: E501
    "help.gitkraken.com/gitkraken-desktop/current": "/gitkraken/release-note",  # noqa: E501
    "help.sogou.com/logo/doodle_logo_list.html": "/sogou/doodles",  # noqa: E501
    "hinatazaka46.com/s/official/news/list": "/hinatazaka46/news",  # noqa: E501
    "hitwh.edu.cn/1024/list.htm": "/hitwh/today",  # noqa: E501
    "hk01.com/hot": "/hk01/hot",  # noqa: E501
    "hk01.com/latest": "/hk01/latest",  # noqa: E501
    "hospital.nju.edu.cn/ggtz/index.html": "/nju/hospital",  # noqa: E501
    "houqin.qdu.edu.cn/tzgg.htm": "/qdu/houqin",  # noqa: E501
    "hqsz.ouc.edu.cn/news.html?typeId=02": "/ouc/hqsz",  # noqa: E501
    "huanbao.bjx.com.cn/yw": "/bjx/huanbao",  # noqa: E501
    "hub.baai.ac.cn/events": "/baai/hub/events",  # noqa: E501
    "huggingface.co/blog": "/huggingface/blog",  # noqa: E501
    "huggingface.co/blog/zh": "/huggingface/blog-zh",  # noqa: E501
    "huxiu.com/moment": "/huxiu/moment",  # noqa: E501
    "idolypride.jp/wp-json/wp/v2/news": "/idolypride/news",  # noqa: E501
    "iec.cnu.edu.cn/ggml/tzgg1/index.htm": "/cnu/iec",  # noqa: E501
    "ieee-security.org/TC/SP-Index.html": "/ieee-security/security-privacy",  # noqa: E501
    "imagemagick.org/script/download.php": "/imagemagick/changelog",  # noqa: E501
    "imiker.com/explore/find": "/imiker/ask/jinghua",  # noqa: E501
    "indiansinkuwait.com/latest-news": "/indiansinkuwait/latest",  # noqa: E501
    "indienova.com/usergames": "/indienova/usergames",  # noqa: E501
    "info-maimai.sega.jp": "/sega/maimaidx/news",  # noqa: E501
    "infoq.cn": "/infoq/recommend",  # noqa: E501
    "insider.finology.in/bullets": "/finology/bullets",  # noqa: E501
    "insider.finology.in/most-viewed": "/finology/most-viewed",  # noqa: E501
    "iqnew.com/post/new_100": "/iqnew/latest",  # noqa: E501
    "it.ouc.edu.cn/_s381/16619/list.psp": "/ouc/it/postgraduate",  # noqa: E501
    "itsc.nju.edu.cn/tzgg/list.htm": "/nju/itsc",  # noqa: E501
    "jiuye.swjtu.edu.cn/career": "/swjtu/jyzpxx",  # noqa: E501
    "jjc.nju.edu.cn/main.htm": "/nju/jjc",  # noqa: E501
    "jlpt.neea.cn": "/neea/jlpt",  # noqa: E501
    "jlwater.com/portal/10000015": "/tingshuitz/nanjing",  # noqa: E501
    "jsjxy.stbu.edu.cn/news": "/stbu/jsjxy",  # noqa: E501
    "juejin.cn/books": "/juejin/books",  # noqa: E501
    "jules.google/docs/changelog": "/google/jules/changelog",  # noqa: E501
    "junhe.com": "/junhe/legal-updates",  # noqa: E501
    "jw.cdu.edu.cn": "/cdu/jwgg",  # noqa: E501
    "jw.qust.edu.cn/jwtz.htm": "/qust/jw",  # noqa: E501
    "jw.scnu.edu.cn/ann/index.html": "/scnu/jw",  # noqa: E501
    "jwb.bnu.edu.cn/tzgg/index.htm": "/bnu/jwb",  # noqa: E501
    "jwc.cnu.edu.cn/tzgg/index.htm": "/cnu/jwc",  # noqa: E501
    "jwc.cupl.edu.cn/index/tzgg.htm": "/cupl/jwc",  # noqa: E501
    "jwc.jlu.edu.cn": "/jlu/jwc",  # noqa: E501
    "jwc.nankai.edu.cn": "/nankai/jwc",  # noqa: E501
    "jwc.ncu.edu.cn/Notices.jsp": "/ncu/jwc",  # noqa: E501
    "jwc.ouc.edu.cn": "/ouc/jwc",  # noqa: E501
    "jwc.qdu.edu.cn/jwtz.htm": "/qdu/jwc",  # noqa: E501
    "jwc.swjtu.edu.cn/vatuu/WebAction": "/swjtu/jwc",  # noqa: E501
    "jwc.wfu.edu.cn": "/wfu/jwc",  # noqa: E501
    "jwgl.ouc.edu.cn/cas/login.action": "/ouc/jwgl",  # noqa: E501
    "kadokawa.com.tw": "/kadokawa/blog",  # noqa: E501
    "kimlaw.or.kr/67": "/kimlaw/thesis",  # noqa: E501
    "kiro.dev": "/kiro/blog",  # noqa: E501
    "konghq.com/blog/*": "/konghq/blog-posts",  # noqa: E501
    "kuaidi100.com": "/kuaidi100/company",  # noqa: E501
    "kunchengblog.com/essay": "/kunchengblog/essay",  # noqa: E501
    "kyc.bjfu.edu.cn": "/bjfu/kjc",  # noqa: E501
    "leetcode.cn": "/leetcode/dailyquestion/solution/cn",  # noqa: E501
    "leetcode.com": "/leetcode/dailyquestion/solution/en",  # noqa: E501
    "leetcode.com/articles": "/leetcode/articles",  # noqa: E501
    "leiphone.com": "/leiphone/newsflash",  # noqa: E501
    "lib.njucm.edu.cn/2899/list.htm": "/njucm/grabszs",  # noqa: E501
    "lib.njxzc.edu.cn/pxyhd/list.htm": "/njxzc/libtzgg",  # noqa: E501
    "lib.scnu.edu.cn/news/zuixingonggao": "/scnu/library",  # noqa: E501
    "lib.xyc.edu.cn/index/tzgg.htm": "/xyu/library",  # noqa: E501
    "library.gxmzu.edu.cn/news/news_list.jsp": "/gxmzu/libzxxx",  # noqa: E501
    "link3.to": "/link3/events",  # noqa: E501
    "literotica.com": "/literotica/new",  # noqa: E501
    "lock.cmpxchg8b.com/articles": "/cmpxchg8b/articles",  # noqa: E501
    "luogu.com.cn/contest/list": "/luogu/contest",  # noqa: E501
    "luxiangdong.com": "/luxiangdong/archive",  # noqa: E501
    "macfilos.com/blog": "/macfilos/blog",  # noqa: E501
    "magazine.raspberrypi.com": "/raspberrypi/magazine",  # noqa: E501
    "magnumphotos.com": "/magnumphotos/magazine",  # noqa: E501
    "manus.im": "/manus/blog",  # noqa: E501
    "mdadmission.pumc.edu.cn/mdweb/site": "/pumc/mdadmission",  # noqa: E501
    "meteor.today": "/meteor/boards",  # noqa: E501
    "modelscope.cn/datasets": "/modelscope/datasets",  # noqa: E501
    "modelscope.cn/models": "/modelscope/models",  # noqa: E501
    "modelscope.cn/studios": "/modelscope/studios",  # noqa: E501
    "mohw.gov.tw": "/mohw/clarification",  # noqa: E501
    "monitor.firefox.com": "/firefox/breaches",  # noqa: E501
    "mp.weixin.qq.com/cgi-bin/announce?action=getannouncementlist&lang=zh_CN": "/wechat/announce",  # noqa: E501
    "mpaypass.com.cn": "/mpaypass/news",  # noqa: E501
    "mrdx.cn*": "/mrdx/today",  # noqa: E501
    "mrinalxdev.github.io/mrinalxblogs/blogs/blog.html": "/mrinalxdev/blog",  # noqa: E501
    "musikguru.de": "/musikguru/news",  # noqa: E501
    "mysql.taobao.org": "/taobao/mysql/monthly",  # noqa: E501
    "nature.com": "/nature/cover",  # noqa: E501
    "nature.com/latest-news": "/nature/news",  # noqa: E501
    "nautiljon.com": "/nautiljon/releases/manga",  # noqa: E501
    "nbd.com.cn": "/nbd/daily",  # noqa: E501
    "nber.org/papers": "/nber/papers",  # noqa: E501
    "ncpssd.cn": "/ncpssd/newlist",  # noqa: E501
    "ncwu.edu.cn/xxtz.htm": "/ncwu/notice",  # noqa: E501
    "ndss-symposium.org": "/ndss-symposium/ndss",  # noqa: E501
    "news.ahjzu.edu.cn/20/list.htm": "/ahjzu/news",  # noqa: E501
    "news.cdu.edu.cn": "/cdu/tzggcdunews",  # noqa: E501
    "news.cnu.edu.cn/xysx/jdxw/index.htm": "/cnu/jdxw",  # noqa: E501
    "news.gamegene.cn/news": "/gamegene/news",  # noqa: E501
    "news.nogizaka46.com/s/n46/news/list": "/nogizaka46/news",  # noqa: E501
    "news.pts.org.tw/curations": "/pts/curations",  # noqa: E501
    "news.pts.org.tw/projects": "/pts/projects",  # noqa: E501
    "newshub.sustech.edu.cn/news": "/sustech/newshub-zh",  # noqa: E501
    "newyjs.snnu.edu.cn": "/snnu/yjs",  # noqa: E501
    "nintendo.co.jp/software/switch/index.html": "/nintendo/eshop/jp",  # noqa: E501
    "nintendo.co.jp/support/switch/system_update/index.html": "/nintendo/system-update",  # noqa: E501
    "nintendo.com.hk/software/switch": "/nintendo/eshop/hk",  # noqa: E501
    "nintendo.com.hk/topics": "/nintendo/news",  # noqa: E501
    "nintendo.com/nintendo-direct/archive": "/nintendo/direct",  # noqa: E501
    "nintendo.com/store/games": "/nintendo/eshop/us",  # noqa: E501
    "nintendoswitch.com.cn": "/nintendo/news/china",  # noqa: E501
    "nintendoswitch.com.cn/software": "/nintendo/eshop/cn",  # noqa: E501
    "njglyy.com/ygb/jypx/jypx.aspx": "/njglyy/ygbjypx",  # noqa: E501
    "notion.so/releases": "/notion/release",  # noqa: E501
    "nowcoder.com": "/nowcoder/recommend",  # noqa: E501
    "nsd.pku.edu.cn": "/pku/nsd/gd",  # noqa: E501
    "nsfw.abskoop.com/wp-json/wp/v2/posts": "/abskoop/nsfw",  # noqa: E501
    "open.spotify.com": "/spotify/top/tracks",  # noqa: E501
    "pair.withgoogle.com/explorables": "/withgoogle/explorables",  # noqa: E501
    "panewslab.com": "/panewslab/news",  # noqa: E501
    "paradigm.xyz/writing": "/paradigm/writing",  # noqa: E501
    "penguinrandomhouse.com/articles": "/penguin-random-house/articles",  # noqa: E501
    "penguinrandomhouse.com/the-read-down": "/penguin-random-house/the-read-down",  # noqa: E501
    "photo.cctv.com/jx": "/cctv/photo/jx",  # noqa: E501
    "physics.cnu.edu.cn/news/index.htm": "/cnu/physics",  # noqa: E501
    "pianyuan.org": "/pianyuan/indexers/pianyuan/results/search/api",  # noqa: E501
    "pingwest.com/status": "/pingwest/status",  # noqa: E501
    "piyao.org.cn/jrpy/index.htm": "/piyao/jrpy",  # noqa: E501
    "pjsekai.sega.jp/news/index.html": "/sega/pjsekai/news",  # noqa: E501
    "pkmer.cn/page/*": "/pkmer/recent",  # noqa: E501
    "plurk.com/anonymous": "/plurk/anonymous",  # noqa: E501
    "plurk.com/hotlinks": "/plurk/hotlinks",  # noqa: E501
    "postman.com/downloads/release-notes": "/postman/release-notes",  # noqa: E501
    "qbittorrent.org/news.php": "/qbittorrent/news",  # noqa: E501
    "qlu.edu.cn/tzggsh/list1.htm": "/qlu/notice",  # noqa: E501
    "quantamagazine.org": "/quantamagazine/archive",  # noqa: E501
    "reactiflux.com/transcripts": "/reactiflux/transcripts",  # noqa: E501
    "readhub.cn/daily": "/readhub/daily",  # noqa: E501
    "red.anthropic.com": "/anthropic/red",  # noqa: E501
    "remnote.com/changelog": "/remnote/changelog",  # noqa: E501
    "research.ke.com/apis/consumer-access/index/contents/page": "/ke/researchResults",  # noqa: E501
    "research.netflix.com": "/netflix/research",  # noqa: E501
    "rjxy.jsu.edu.cn/index/tzgg1.htm": "/jsu/rjxy",  # noqa: E501
    "rockthejvm.com": "/rockthejvm/articles",  # noqa: E501
    "roll.caijing.com.cn/index1.html": "/caijing/roll",  # noqa: E501
    "rszhaopin.bit.edu.cn": "/bit/rszhaopin",  # noqa: E501
    "rustcc.cn": "/rustcc/news",  # noqa: E501
    "sakurazaka46.com/s/s46/news/list": "/sakurazaka46/news",  # noqa: E501
    "scc.hnu.edu.cnundefined": "/hnu/careers",  # noqa: E501
    "scse.uestc.edu.cn": "/uestc/scse",  # noqa: E501
    "scss.bupt.edu.cn": "/bupt/scss/tzgg",  # noqa: E501
    "scvtc.edu.cn/ggfw1/xygg.htm": "/scvtc/xygg",  # noqa: E501
    "sessionserver.mojang.com/blockedservers": "/minecraft/blockedservers",  # noqa: E501
    "seugs.seu.edu.cn/26671/list.htm": "/seu/yjs",  # noqa: E501
    "sh.eastday.com": "/eastday/sh",  # noqa: E501
    "shortcuts.sspai.com/*": "/sspai/shortcuts",  # noqa: E501
    "sice.uestc.edu.cn": "/uestc/sice",  # noqa: E501
    "sigsac.org/ccs.html": "/sigsac/ccs",  # noqa: E501
    "smkxxy.cnu.edu.cn/tzgg3/index.htm": "/cnu/smkxxy",  # noqa: E501
    "source.android.com/docs/security/bulletin/asb-overview": "/android/security-bulletin",  # noqa: E501
    "ss.scnu.edu.cn/tongzhigonggao": "/scnu/ss",  # noqa: E501
    "sspai.com/matrix": "/sspai/matrix",  # noqa: E501
    "sspai.com/series": "/sspai/series",  # noqa: E501
    "sspai.com/topics": "/sspai/topics",  # noqa: E501
    "stbu.edu.cn/html/news/xueyuan": "/stbu/xyxw",  # noqa: E501
    "strategyand.pwc.com/at/en/functions/sustainability-strategy/publications.html": "/pwc/strategyand/sustainability",  # noqa: E501
    "stxy.jsu.edu.cn/index/tzgg1.htm": "/jsu/stxy",  # noqa: E501
    "supchina.com/podcasts": "/supchina/podcasts",  # noqa: E501
    "support.typora.io": "/typora/changelog",  # noqa: E501
    "sustainabilitymag.com/articles": "/sustainabilitymag/articles",  # noqa: E501
    "swj.dl.gov.cn/col/col4296/index.html": "/tingshuitz/dalian",  # noqa: E501
    "szse.cn/disclosure/notice/company/index.html": "/szse/notice",  # noqa: E501
    "tech.meituan.com": "/meituan/tech",  # noqa: E501
    "tech.sina.com.cn/chuangshiji": "/sina/csj",  # noqa: E501
    "techcrunch.com": "/techcrunch/news",  # noqa: E501
    "techflowpost.com": "/techflowpost/express",  # noqa: E501
    "telegram.org/blog": "/telegram/blog",  # noqa: E501
    "thepaper.cn": "/thepaper/featured",  # noqa: E501
    "tiddlywiki.com": "/tiddlywiki/releases",  # noqa: E501
    "towardsdatascience.com/latest": "/towardsdatascience/latest",  # noqa: E501
    "tradingview.com/support/solutions/43000673888-tradingview-desktop-releases-and-release-notes": "/tradingview/desktop",  # noqa: E501
    "trow.cc": "/trow/portal",  # noqa: E501
    "twreporter.org": "/twreporter/newest",  # noqa: E501
    "unraid.net/community/apps": "/unraid/community-apps",  # noqa: E501
    "unusualwhales.com/news": "/unusualwhales/news",  # noqa: E501
    "uowji.ccnu.edu.cn/xwzx/tzgg.htm": "/ccnu/wu",  # noqa: E501
    "usenix.org/conferences/all": "/usenix/usenix-security-sympoium",  # noqa: E501
    "utgd.net": "/utgd/timeline",  # noqa: E501
    "vertikal.net/en/news": "/vertikal/latest",  # noqa: E501
    "wanqu.co": "/wanqu/news",  # noqa: E501
    "wap.zuel.edu.cn": "/zuel/notice",  # noqa: E501
    "warp.dev": "/warp/blog",  # noqa: E501
    "web.stockedge.com/daily-updates/news": "/stockedge/daily-updates/news",  # noqa: E501
    "webplus.nju.edu.cn/_s25/main.psp": "/nju/hqjt",  # noqa: E501
    "weekly.caixin.com": "/caixin/weekly",  # noqa: E501
    "wen.woshipm.com": "/woshipm/wen",  # noqa: E501
    "wfdf.sport/news": "/wfdf/news",  # noqa: E501
    "windsurf.com": "/windsurf/changelog",  # noqa: E501
    "www.acgvinyl.com/col.jsp?id=103": "/acgvinyl/news",  # noqa: E501
    "www.adquan.com": "/adquan/case_library",  # noqa: E501
    "www.afr.com": "/afrNavigation path, can be found in the URL of the page",  # noqa: E501
    "www.afr.com/latest": "/afr/latest",  # noqa: E501
    "www.aibase.com": "/aibase/news",  # noqa: E501
    "www.ainvest.com/news": "/ainvest/news",  # noqa: E501
    "www.ainvest.com/news/articles-latest": "/ainvest/article",  # noqa: E501
    "www.anthropic.com/engineering": "/anthropic/engineering",  # noqa: E501
    "www.anthropic.com/news": "/anthropic/news",  # noqa: E501
    "www.anthropic.com/research": "/anthropic/research",  # noqa: E501
    "www.azul.com": "/azul/downloads",  # noqa: E501
    "www.bilibili.com": "/bilibili/hot-search",  # noqa: E501
    "www.cffex.com.cn": "/cffex/announcement",  # noqa: E501
    "www.chiark.greenend.org.uk/~sgtatham/putty/changes.html": "/putty/changes",  # noqa: E501
    "www.coolpc.com.tw": "/coolpc/news",  # noqa: E501
    "www.csust.edu.cn/tggs.htm": "/csust/tggs",  # noqa: E501
    "www.csust.edu.cn/xkxs.htm": "/csust/xkxs",  # noqa: E501
    "www.ctbu.edu.cn": "/ctbu/xxgg",  # noqa: E501
    "www.dgtle.com": "/dgtle/video",  # noqa: E501
    "www.dongqiudi.com/special/48": "/dongqiudi/daily",  # noqa: E501
    "www.eastday.com": "/eastday/portrait",  # noqa: E501
    "www.eeo.com.cn": "/eeo/kuaixun",  # noqa: E501
    "www.egsea.com/news/flash-list?per-page=30": "/egsea/flash",  # noqa: E501
    "www.foreverblog.cn/feeds.html": "/foreverblog/feeds",  # noqa: E501
    "www.gaoyu.me": "/gaoyu/blog",  # noqa: E501
    "www.gcores.com": "/gcores/videos",  # noqa: E501
    "www.gdufs.edu.cn/gwxw/gwxw1.htm": "/gdufs/news",  # noqa: E501
    "www.hotukdeals.com": "/hotukdeals/hottest",  # noqa: E501
    "www.hpoi.net/bannerItem/list": "/hpoi/bannerItem",  # noqa: E501
    "www.hzwgc.com/public/stop_the_water": "/tingshuitz/hangzhou",  # noqa: E501
    "www.ifanr.com": "/ifanr/digest",  # noqa: E501
    "www.iwara.tv": "/iwara/subscriptions",  # noqa: E501
    "www.iyingdi.com": "/lfsyd/home",  # noqa: E501
    "www.j-test.com": "/j-test/news",  # noqa: E501
    "www.jianshu.com": "/jianshu/home",  # noqa: E501
    "www.jingzhengu.com": "/jingzhengu/news",  # noqa: E501
    "www.jou.edu.cn/index/tzgg.htm": "/jou/tzgg",  # noqa: E501
    "www.jsu.edu.cn/index/tzgg.htm": "/jsu/notice",  # noqa: E501
    "www.last-origin.com": "/last-origin/news",  # noqa: E501
    "www.ltaaa.cn": "/ltaaa/article",  # noqa: E501
    "www.miyuki.jp/s/y10/news/list": "/miyuki/news",  # noqa: E501
    "www.modelscope.cn/learn": "/modelscope/learn",  # noqa: E501
    "www.niaogebiji.com/pc/bulletin/index": "/niaogebiji/today",  # noqa: E501
    "www.njit.edu.cn": "/njit/tzgg",  # noqa: E501
    "www.njxzc.edu.cn/89/list.htm": "/njxzc/tzgg",  # noqa: E501
    "www.notateslaapp.com/software-updates/history": "/notateslaapp/ota",  # noqa: E501
    "www.ornl.gov": "/ornl/all-news",  # noqa: E501
    "www.perplexity.ai": "/perplexity/changelog",  # noqa: E501
    "www.pixiv.net/bookmark_new_illust.php": "/pixiv/user/illustfollows",  # noqa: E501
    "www.python.org": "/python/release",  # noqa: E501
    "www.shmeea.edu.cn/page/04000/index.html": "/shmeea/self-study",  # noqa: E501
    "www.shoppingdesign.com.tw/post": "/shoppingdesign/posts",  # noqa: E501
    "www.sme.buaa.edu.cn": "/buaa版块路径，默认为 `tzgg`（通知公告）",  # noqa: E501
    "www.stcn.com": "/stcn/article/list/kx",  # noqa: E501
    "www.taiwanmobile.com/cs/public/servAnn/queryList.htm?type=1": "/taiwanmobile/rate-plans",  # noqa: E501
    "www.tctmd.com/news/conference-news": "/tctmd/conference-news",  # noqa: E501
    "www.tmtpost.com": "/tmtpost/new",  # noqa: E501
    "www.tmtpost.com/nictation": "/tmtpost/nictation",  # noqa: E501
    "www.trendforce.com": "/trendforce/news",  # noqa: E501
    "www.typeless.com/help/release-notes": "/typeless/changelog",  # noqa: E501
    "www.ulapia.com": "/ulapia/research/latest",  # noqa: E501
    "www.wainao.me": "/wainao/wainao-reads",  # noqa: E501
    "www.warhammer-community.com/en-gb/all-news-and-features": "/warhammer-community/news",  # noqa: E501
    "www.wchscu.cn": "/wchscu/recruit",  # noqa: E501
    "www.weather.gov.hk/en/wxinfo/currwx/current.htm": "/hko/weather",  # noqa: E501
    "www.wellcee.com": "/wellcee/support-city",  # noqa: E501
    "www.xlmp4.com": "/domp4/latest_movie_bt",  # noqa: E501
    "www.xswater.com/gongshui/channels/227.html": "/tingshuitz/xiaoshan",  # noqa: E501
    "www.xyc.edu.cn/index/tzgg.htm": "/xyu/index/tzgg",  # noqa: E501
    "www.yilinzazhi.com": "/yilinzazhi/latest",  # noqa: E501
    "www.zhihu.com/pub/weekly": "/zhihu/weekly",  # noqa: E501
    "www2.scut.edu.cn/graduate/14562/list.htm": "/scut/yjs",  # noqa: E501
    "x410.dev": "/x410/news",  # noqa: E501
    "xboxfan.com": "/xboxfan/news",  # noqa: E501
    "xgc.nuist.edu.cn": "/nuist/xgc",  # noqa: E501
    "xiaomiyoupin.com": "/xiaomiyoupin/latest",  # noqa: E501
    "xueqiu.com/statuses/hots.json": "/xueqiu/hots",  # noqa: E501
    "xueqiu.com/today": "/xueqiu/today",  # noqa: E501
    "yicai.com": "/yicai/carousel",  # noqa: E501
    "yicai.com/brief": "/yicai/brief",  # noqa: E501
    "yjs.gxmzu.edu.cn/tzgg/zsgg.htm": "/gxmzu/yjszsgg",  # noqa: E501
    "yjsswjt.com/zxdt_list.jsp": "/tingshuitz/yangjiang",  # noqa: E501
    "yjsy.gzhu.edu.cn/zsxx/zsdt/zsdt.htm": "/gzhu/yjs",  # noqa: E501
    "yjsy.scau.edu.cn/208/list.htm": "/scau/yjsy",  # noqa: E501
    "yxdown.com": "/yxdown/recommend",  # noqa: E501
    "yystv.cn/docs": "/yystv/docs",  # noqa: E501
    "yysub.net": "/yyets/today",  # noqa: E501
    "yz.chsi.com.cn": "/chsi/hotnews",  # noqa: E501
    "yz.chsi.com.cn/kyzx/kydt": "/chsi/kydt",  # noqa: E501
    "yz.cuc.edu.cn/8549/list.htm": "/cuc/yz",  # noqa: E501
    "yz.jou.edu.cn/index/zxgg.htm": "/jou/yztzgg",  # noqa: E501
    "yz.kaoyan.com/ecnu/tiaoji": "/ecnu/yjs",  # noqa: E501
    "yz.ouc.edu.cn/5926/list.htm": "/ouc/yjs",  # noqa: E501
    "yz.scnu.edu.cn/tongzhigonggao/ssgg": "/scnu/yjs",  # noqa: E501
    "yz.tongji.edu.cn/zsxw/ggtz.htm": "/tongji/yjs",  # noqa: E501
    "yzb.scau.edu.cn/2136/list1.htm": "/scau/yzb",  # noqa: E501
    "zcc.nju.edu.cn/tzgg/gyfytdglk/index.html": "/nju/zcc",  # noqa: E501
    "zed.dev": "/zed/blog",  # noqa: E501
    "zotero.org": "/zotero/versions",  # noqa: E501
    "zs.gs.upc.edu.cn/sszs/list.htm": "/upc/yjs",  # noqa: E501
}
# --- END RSSHUB_URL_MAP ---

# Maps normalized URL paths (scheme-stripped, no trailing slash) → Olshansk raw feed URL.
# When a user pastes e.g. https://cursor.com/blog, we return the feed directly.
# AUTO-GENERATED — do not edit by hand. Run scripts/sync_olshansk_feeds.py to update.
# --- BEGIN OLSHANSK_FEED_MAP (auto-generated) ---
OLSHANSK_FEED_MAP: dict[str, str] = {
    "chanderramesh.com/writing": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_chanderramesh.xml",  # noqa: E501
    "cursor.com/blog": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_cursor.xml",  # noqa: E501
    "dagster.io/blog": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_dagster.xml",  # noqa: E501
    "developers.googleblog.com/search/?technology_categories=AI": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_google_ai.xml",  # noqa: E501
    "github.com/anthropics/claude-code/blob/main/CHANGELOG.md": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_changelog_claude_code.xml",  # noqa: E501
    "hamel.dev": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_hamel.xml",  # noqa: E501
    "ollama.com/blog": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_ollama.xml",  # noqa: E501
    "openai.com/news/research": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_openai_research.xml",  # noqa: E501
    "thinkingmachines.ai/blog": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_thinkingmachines.xml",  # noqa: E501
    "windsurf.com/blog": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_windsurf_blog.xml",  # noqa: E501
    "windsurf.com/changelog": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_windsurf_changelog.xml",  # noqa: E501
    "windsurf.com/changelog/windsurf-next": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_windsurf_next_changelog.xml",  # noqa: E501
    "www.deeplearning.ai/the-batch": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_the_batch.xml",  # noqa: E501
    "www.paulgraham.com/articles.html": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_paulgraham.xml",  # noqa: E501
    "www.surgehq.ai/blog": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_blogsurgeai.xml",  # noqa: E501
    "x.ai/news": "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_xainews.xml",  # noqa: E501
}
# --- END OLSHANSK_FEED_MAP ---

# ── Regex patterns ─────────────────────────────────────────────────

CHANNEL_ID_PATTERNS = [
    re.compile(r'"externalId"\s*:\s*"(UC[\w-]{22})"'),
    re.compile(r"/channel/(UC[\w-]{22})"),
    re.compile(r'"channelId"\s*:\s*"(UC[\w-]{22})"'),
]

BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

_TWITTER_BLOCKED = {"home", "explore", "search", "settings", "i"}


# ── Pure resolvers (no network) ────────────────────────────────────


def resolve_twitter(parsed: urlparse) -> dict:
    """Extract handle from a Twitter/X URL."""
    path = parsed.path.strip("/")
    handle = path.split("/")[0].lstrip("@") if path else ""
    if not handle or handle.lower() in _TWITTER_BLOCKED:
        raise ValueError(f"Could not extract handle from URL: {parsed.geturl()}")
    return {"source_type": "twitter", "fields": {"handle": handle}, "suggested_tags": []}


def resolve_arxiv(parsed: urlparse) -> dict:
    """Resolve arxiv.org URLs to RSS feed URLs."""
    path = parsed.path.strip("/")

    m = re.match(r"(?:abs|pdf)/(\d{4}\.\d{4,5})", path)
    if m:
        paper_id = m.group(1)
        return {
            "source_type": "arxiv",
            "fields": {
                "url": f"https://export.arxiv.org/api/query?search_query=id:{paper_id}&max_results=50",
                "name": f"arXiv:{paper_id}",
            },
            "suggested_tags": ["research"],
        }

    m = re.match(r"list/([\w.]+)", path)
    if m:
        cat = m.group(1)
        return {
            "source_type": "arxiv",
            "fields": {
                "url": f"https://rss.arxiv.org/rss/{cat}",
                "name": f"arXiv:{cat}",
            },
            "suggested_tags": ["research"],
        }

    raise ValueError(f"Could not parse arXiv URL: {parsed.geturl()}")


def resolve_xiaohongshu(parsed: urlparse) -> dict:
    """Extract user_id from Xiaohongshu profile URLs."""
    path = parsed.path.strip("/")
    m = re.match(r"user/profile/([a-fA-F0-9]+)", path)
    if m:
        user_id = m.group(1)
        return {
            "source_type": "xiaohongshu",
            "fields": {"user_id": user_id, "name": f"XHS:{user_id[:8]}"},
            "suggested_tags": [],
        }
    raise ValueError(f"Could not parse Xiaohongshu URL: {parsed.geturl()}")


def resolve_luma(parsed: urlparse) -> dict:
    """Extract handle from lu.ma URLs."""
    path = parsed.path.strip("/")
    handle = path.split("/")[0] if path else ""
    if not handle:
        raise ValueError(f"Could not extract handle from Luma URL: {parsed.geturl()}")
    return {"source_type": "luma", "fields": {"handle": handle}, "suggested_tags": []}


def resolve_rsshub(parsed: urlparse) -> dict:
    """Extract route from rsshub.app URLs."""
    route = parsed.path.strip("/")
    if not route:
        raise ValueError("Empty RSSHub route")
    name = route.split("/")[-1]
    return {
        "source_type": "rsshub",
        "fields": {"route": route, "name": f"RSSHub:{name}"},
        "suggested_tags": [],
    }


def _url_lookup_keys(parsed: urlparse) -> list[str]:
    """Return candidate lookup keys for a parsed URL, from most to least specific.

    Tries exact host+path, www-stripped host+path, and host-only fallback.
    Deduplicates while preserving order.
    """
    hostname = parsed.hostname or ""
    host = hostname.removeprefix("www.")
    path = parsed.path.rstrip("/")
    seen: set[str] = set()
    keys = []
    for key in (f"{hostname}{path}", f"www.{host}{path}", f"{host}{path}", hostname, host):
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def resolve_rsshub_for_url(parsed: urlparse) -> dict | None:
    """Return an RSSHub source if the pasted website URL has a known RSSHub route."""
    for key in _url_lookup_keys(parsed):
        route = RSSHUB_URL_MAP.get(key)
        if route:
            name = route.split("/")[-1]
            return {
                "source_type": "rsshub",
                "fields": {"route": route, "name": f"RSSHub:{name}"},
                "suggested_tags": [],
            }
    return None


def resolve_olshansk(parsed: urlparse) -> dict | None:
    """Return an RSS source using the Olshansk feed mirror if the URL is known."""
    for key in _url_lookup_keys(parsed):
        feed_url = OLSHANSK_FEED_MAP.get(key)
        if feed_url:
            name = key.split("/")[-1].replace("-", " ").replace(".", " ").title()
            return {
                "source_type": "rss",
                "fields": {"url": feed_url, "name": name},
                "suggested_tags": [],
            }
    return None


def extract_title(html: str) -> str:
    """Extract <title> or og:title from HTML."""
    m = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"',
        html,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""
