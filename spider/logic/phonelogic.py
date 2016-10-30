# !/usr/bin/python3.4
# -*-coding:utf-8-*-
# Created by Smartdo Co.,Ltd. on 2016/10/14.
# 功能:
#
import tool.log
from action.url import *
from action.phonesql import *
from config.config import *
from tool.jfile.file import *
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ProcessPoolExecutor
from spider.download.ratedownload import *
from spider.parse.phonedetail import *

# 日志
tool.log.setup_logging()
logger = logging.getLogger(__name__)
loggers = logging.getLogger("smart")

DATA_DIR = getconfig()["datadir"]


# 单类目抓取
def unitlogic(url, mysqlconfig):
    global DATA_DIR
    # 抓取的类目URL
    catchurl = url[1]
    # 类目名
    catchname = url[2]
    # 类目ID
    id = url[0]
    # 大类名
    bigpname = url[4]
    # 数据库
    db = url[6]

    todays = tool.log.TODAYTIME
    year = todaystring(1)

    if getconfig()["ipinmysql"]:
        where = "mysql"
    else:
        where = "local"

    keepdir = createjia(DATA_DIR + "/data/items/" + year + "/" + bigpname.replace(" ", "") + "/" + todays)
    detaildir = createjia(DATA_DIR + "/data/detail/" + year + "/" + bigpname.replace(" ", "") + "/" + todays + "/" + id)

    listheader = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Connection": "keep-alive",
        "Accept-Language": "en-US;q=0.8,en;q=0.5",
        "Upgrade-Insecure-Requests": "1",
        'Host': 'www.amazon.com'
    }

    parsecontent = {}
    if fileexsit(keepdir + "/" + id + ".md"):
        with open(keepdir + "/" + id + ".md", "rb") as f:
            parsecontent = stringToObject(f.read().decode("utf-8", "ignore"))
    else:
        listcontent = ratedownload(url=catchurl, where=where, config=mysqlconfig, header=listheader)
        if listcontent:
            parsecontent = phonelistparse(listcontent.decode("utf-8", "ignore"))
            if parsecontent:
                with open(keepdir + "/" + id + ".md", "wb") as f:
                    f.write(objectToString(parsecontent).encode("utf-8"))
                phoneinsertlist(parsecontent, url)

    for asin in parsecontent:
        # smallrank-asin
        smallrank = parsecontent[asin][0]
        detailname = str(smallrank) + "-" + asin
        rankeep = detaildir + "/" + detailname
        if fileexsit(rankeep + ".md"):
            loggers.warning("存在!" + rankeep)
            continue
        if fileexsit(rankeep + ".emd"):
            loggers.warning("存在(页面找不到）)!" + rankeep)
            continue
        detailurl = "https://www.amazon.com/dp/" + asin

        if fileexsit(rankeep + ".html"):
            with open(rankeep + ".html", "rb") as ff:
                detailpage = ff.read()
        else:
            detailheader = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Connection": "keep-alive",
                "Accept-Language": "en-US;q=0.8,en;q=0.5",
                "Upgrade-Insecure-Requests": "1",
                'Host': 'www.amazon.com'
            }
            detailpage = ratedownload(url=detailurl, where=where, config=mysqlconfig, header=detailheader)
            if detailpage == None:
                continue
            if detailpage == 0:
                with open(rankeep + ".emd", "wt") as f:
                    f.write("1")
                continue
            else:
                with open(rankeep + ".html", "wb") as f:
                    f.write(detailpage)
        try:
            pinfo = phonedetailparse(detailpage.decode("utf-8", "ignore"))
        except:
            logger.error("解析詳情頁出錯:" + detailurl)
            savedetailerror(detailpage, asin)
            continue
        try:
            pinfo["smallrank"] = int(smallrank)
        except:
            pinfo["smallrank"] = -1
        pinfo["title"] = parsecontent[asin][3]
        pinfo["price"] = parsecontent[asin][4]
        pinfo["asin"] = asin
        pinfo["url"] = detailurl
        pinfo["img"] = parsecontent[asin][2]
        if len(pinfo["img"]) > 240:
            pinfo["img"] = ""
        pinfo["name"] = catchname
        pinfo["bigname"] = bigpname
        pinfo["id"] = todays + "-" + detailname

        # 插入数据库，失败也不要紧
        phoneinsertexsitlist(pinfo, url)
        phoneinsertpmysql(pinfo, db, id)

    # 成功
    logger.warning(todays + "|" + bigpname + "|" + db + ":" + id + " completed")


# 单进程抓取
def processlogic(processurls, mysqlconfig):
    logger.error(getconfig()["catchurl"])
    logger.debug(processurls)
    for url in processurls:
        try:
            unitlogic(url, mysqlconfig)
        except Exception as err:
            logger.error("單進程抓錯異常：")
            logger.error(url)
            logger.error(err, exc_info=1)


# 多进程抓取
def ratelogic(category=["Appliances"], processnum=1, limitnum=20000):
    allconfig = getconfig()
    try:
        mysqlconfig = allconfig["basedb"]
    except:
        raise Exception("基础数据库配置出错")
    # 创建今天的数据库
    createtodaydb()
    urls = list(usaurl(config=mysqlconfig, category=category, limitnum=limitnum))
    tasklist = devidelist(urls, processnum)
    with ThreadPoolExecutor(max_workers=processnum) as e:
        for task in tasklist:
            f = e.submit(processlogic, tasklist[task], mysqlconfig)


def savedetailerror(content, asin):
    createjia(tool.log.BASE_DIR + "/data/phonerrdetail")
    k = tool.log.BASE_DIR + "/data/phonerrdetail/" + asin + ".html"
    if fileexsit(k):
        pass
    else:
        with open(k, "wb") as f:
            f.write(content)
        logger.error("排名强制标记:" + k)


# 创建今天的数据库
def createtodaydb():
    config = getconfig()["db"]
    db = Mysql(config)
    sql = '''
CREATE TABLE `{tablename}` (
 `id` VARCHAR(255),
  `purl` varchar(255) DEFAULT NULL COMMENT '父类类目链接',
  `dbname` varchar(255) DEFAULT NULL COMMENT 'dbname',
  `col1` varchar(255) DEFAULT NULL COMMENT '预留字段',
  `price` varchar(255) DEFAULT NULL COMMENT '价格',
  `img` varchar(255) DEFAULT NULL COMMENT '图像',
  `iscatch` tinyint(4) DEFAULT '0' COMMENT '已抓取是1',
  `smallrank` INT NULL COMMENT '小类排名',
  `name` VARCHAR(255) NULL COMMENT '小类名',
  `bigname` VARCHAR(255) NULL COMMENT '大类名',
  `title` TINYTEXT NULL COMMENT '商品标题',
  `asin` VARCHAR(255) NULL,
  `url` VARCHAR(255) NULL,
  `rank` INT NULL COMMENT '大类排名',
  `soldby` VARCHAR(255) NULL COMMENT '卖家',
  `shipby` VARCHAR(255) NULL COMMENT '物流',
  `score` FLOAT NULL COMMENT '打分',
  `commentnum` INT NULL COMMENT '评论数',
  `commenttime` VARCHAR(255) NULL COMMENT '第一条评论时间',
  `createtime` DATETIME NULL,
  PRIMARY KEY (`id`) )ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='类目表';
    '''.format(tablename=tool.log.TODAYTIME)
    try:
        db.ExecNonQuery(sql)
        logger.info(tool.log.TODAYTIME + "创建成功")
    except Exception as err:
        logger.info(tool.log.TODAYTIME + "创建失败")


if __name__ == "__main__":
    a = time.clock()
    changeconfig("catchbywhich", "bigpname")
    changeconfig("catchurl", ["Appliances", "Arts_ Crafts & Sewing"])
    processnum = 2
    ratelogic(getconfig()["catchurl"], processnum, 6)
    b = time.clock()
    print('运行时间：' + timetochina(b - a))