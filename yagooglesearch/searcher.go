package yagooglesearch

import (
	"fmt"
	"github.com/gocolly/colly"
	"github.com/gocolly/colly/proxy"
	"github.com/gocolly/colly/queue"
	"log"
	"net/url"
	"strings"
	"sync"
	"time"
)

// SearchClient 结构体保持不变
type SearchClient struct {
	Config           SearchClientConfig
	Collector        *colly.Collector
	Queue            *queue.Queue
	searchResultList []any
	foundUrls        map[string]bool
	wg               sync.WaitGroup // 【新】使用 WaitGroup 来进行同步
}

// SearchClientConfig 接口保持不变
type SearchClientConfig struct {
	Query                         string
	Tld                           string
	LangHtmlUI                    string
	LangResult                    string
	Num                           int
	Start                         int
	MaxSearchResultUrlsToReturn   int
	UserAgent                     string
	Proxies                       []string
	Verbosity                     bool
	Parallelism                   int
	RandomDelay                   time.Duration
	YagooglesearchManagesHttp429s bool
	Http429CoolOffTimeInMinutes   int
}

// NewSearchClient 接口保持不变
func NewSearchClient(config SearchClientConfig) (*SearchClient, error) {
	// (这部分基本不变，只是初始化了 SearchClient)
	if config.Query == "" {
		return nil, fmt.Errorf("query cannot be empty")
	}
	if config.Tld == "" {
		config.Tld = "com"
	}
	if config.LangHtmlUI == "" {
		config.LangHtmlUI = "en"
	}
	if config.Num == 0 {
		config.Num = 100
	}
	if config.Parallelism == 0 {
		config.Parallelism = 1
	} // 【注意】默认并行度改为1，增加初始成功率
	if config.RandomDelay == 0 {
		config.RandomDelay = 5 * time.Second
	} // 默认增加延迟

	c := colly.NewCollector(
		colly.Async(true),
		colly.UserAgent(config.UserAgent),
		// 【新】自动处理Cookie
		colly.AllowURLRevisit(),
	)

	// 【新】增强请求头，使其更像浏览器
	c.OnRequest(func(r *colly.Request) {
		r.Headers.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9")
		r.Headers.Set("Accept-Language", "en-US,en;q=0.9")
		if r.Ctx.Get("is_search") != "" {
			r.Headers.Set("Referer", "https://www.google.com/")
		}
		if config.Verbosity {
			log.Println("Visiting", r.URL.String())
		}
	})

	c.Limit(&colly.LimitRule{
		DomainGlob:  "*.google.*",
		Parallelism: config.Parallelism,
		RandomDelay: config.RandomDelay,
	})

	if len(config.Proxies) > 0 {
		rp, err := proxy.RoundRobinProxySwitcher(config.Proxies...)
		if err != nil {
			return nil, fmt.Errorf("failed to create proxy switcher: %w", err)
		}
		c.SetProxyFunc(rp)
	}

	q, _ := queue.New(config.Parallelism, &queue.InMemoryQueueStorage{MaxSize: 10000})

	sc := &SearchClient{
		Config:           config,
		Collector:        c,
		Queue:            q,
		searchResultList: []any{},
		foundUrls:        make(map[string]bool),
	}

	// 统一设置回调
	sc.setupCallbacks()
	return sc, nil
}

// setupCallbacks 包含所有的事件处理逻辑
func (sc *SearchClient) setupCallbacks() {
	c := sc.Collector

	// 【核心改造】只使用colly内置方法来解析HTML
	c.OnHTML("div#search div.g", func(e *colly.HTMLElement) {
		// e 现在代表一个 <div class="g"> 元素，也就是一个搜索结果块

		if len(sc.searchResultList) >= sc.Config.MaxSearchResultUrlsToReturn {
			return
		}

		// 1. 查找链接URL
		// 我们需要找这个div.g块里面的第一个<a>标签的href属性
		// 注意：ChildAttr找到的是第一个匹配的子元素，这通常就是标题链接
		link := e.ChildAttr("a", "href")
		// (可以加入你之前的 filterSearchResultUrls 逻辑)
		// ...

		// 2. 过滤和去重
		if link != "" && strings.HasPrefix(link, "http") && !strings.Contains(link, "google.com") {
			if _, found := sc.foundUrls[link]; !found {
				sc.foundUrls[link] = true

				// 3. 如果需要详细输出，提取标题和描述
				if sc.Config.Verbosity {
					// 使用 e.ChildText 查找标题(h3)和描述
					// e 是 <div class="g">, h3 是它的子元素
					title := e.ChildText("h3")

					// Google的描述通常在一个特定的div里，我们也可以用ChildText，
					// 但选择器可能需要更精确。这个选择器表示在<div class="g">下
					// 找一个同样是div且属性data-sncf='2'的元素
					desc := e.ChildText("div[data-sncf='2']")

					result := map[string]any{
						"rank":        len(sc.searchResultList) + 1,
						"title":       strings.TrimSpace(title),
						"description": strings.TrimSpace(desc),
						"url":         link,
					}
					sc.searchResultList = append(sc.searchResultList, result)
				} else {
					// 只保存URL
					sc.searchResultList = append(sc.searchResultList, link)
				}

				if sc.Config.Verbosity {
					log.Printf("Found unique URL #%d: %s", len(sc.searchResultList), link)
				}
			}
		}
	})

	// OnHTML: 查找“下一页”链接
	c.OnHTML("a#pnnext[href]", func(e *colly.HTMLElement) {
		if len(sc.searchResultList) >= sc.Config.MaxSearchResultUrlsToReturn {
			log.Println("Max search results reached. Not visiting next page.")
			return
		}
		// 【关键】找到了下一页，就把它加入队列
		nextPageLink := e.Request.AbsoluteURL(e.Attr("href"))
		log.Println("Found next page link, adding to queue:", nextPageLink)
		sc.wg.Add(1) // 增加一个等待任务
		sc.Queue.AddURL(nextPageLink)
	})

	// OnResponse: 检查是否是验证页面，并在所有请求完成后通知WaitGroup
	c.OnResponse(func(r *colly.Response) {
		// 检查是否是被拦截的页面
		bodyStr := string(r.Body)
		if strings.Contains(bodyStr, "如果您在几秒钟内没有被重定向") || strings.Contains(bodyStr, "enablejs") {
			log.Println("!!! Google human verification page detected! Try using a proxy or reducing parallelism/delay. !!!")
		}
	})

	// OnError: 处理错误
	c.OnError(func(r *colly.Response, err error) {
		log.Printf("Request URL: %s failed with response code %d, Error: %v", r.Request.URL, r.StatusCode, err)
		sc.wg.Done() // 【重要】请求出错，也必须算作任务完成
	})

	// OnScraped: 当一个页面的所有OnHTML回调都执行完毕后触发
	c.OnScraped(func(r *colly.Response) {
		// 只有在搜索页面完成后，才标记任务完成
		if r.Ctx.Get("is_search") != "" {
			log.Printf("Finished scraping: %s", r.Request.URL)
			sc.wg.Done() // 【重要】一个搜索任务完成
		}
	})
}

// 【核心改造】Search 函数
func (sc *SearchClient) Search() ([]any, error) {
	// 【阶段一：预热】
	// 先访问一次首页，让colly的cookie jar获取初始cookie，这个过程是同步的。
	log.Println("Phase 1: Warming up session by visiting Google homepage...")
	warmupCollector := sc.Collector.Clone() // 使用克隆的collector进行预热，避免干扰主任务
	err := warmupCollector.Visit(fmt.Sprintf("https://www.google.%s/", sc.Config.Tld))
	if err != nil {
		log.Printf("Warning: Failed to warm up session, but will proceed. Error: %v", err)
	} else {
		log.Println("Warm-up successful, session cookies should be stored.")
	}

	// 【阶段二：执行搜索】
	log.Println("Phase 2: Starting main search task...")

	// 构造初始搜索URL
	baseURL := fmt.Sprintf("https://www.google.%s/search", sc.Config.Tld)
	params := url.Values{}
	params.Set("q", sc.Config.Query)
	params.Set("num", fmt.Sprintf("%d", sc.Config.Num))
	params.Set("hl", sc.Config.LangHtmlUI)
	initialURL := baseURL + "?" + params.Encode()

	// 设置上下文，标记这是一个搜索请求
	ctx := colly.NewContext()
	ctx.Put("is_search", "true")

	// 启动队列，但现在我们用WaitGroup来等待
	//go func() {
	// q.Run会阻塞，直到队列为空并且没有活动的消费者
	// 这意味着当所有翻页任务都完成后，它会自动退出
	sc.Queue.Run(sc.Collector)
	//}()

	// 将第一个任务加入队列，并设置等待数为1
	sc.wg.Add(1)
	err = sc.Queue.AddURL(initialURL)
	if err != nil {
		sc.wg.Done() // 如果添加失败，也得减少等待数
		return nil, fmt.Errorf("failed to add initial URL: %w", err)
	}

	// 【关键】等待所有任务（初始搜索+所有翻页）完成
	sc.wg.Wait()

	log.Println("Search process finished.")
	return sc.searchResultList, nil
}
