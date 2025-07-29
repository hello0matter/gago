package main

import (
	"fmt"
	"github.com/PuerkitoBio/goquery"
	gosearch "goga/yagooglesearch"
	"log"
	"net/http"
	"strings"
	"time"
)

// =================================================================
// 模块 2: 网站分析
// =================================================================

type AnalyzeResult struct {
	FinalURL string
	GAPages  []string
}

// analyzeSite 对指定的URL进行爬取和分析
func analyzeSite(startURL string, userAgent string) (*AnalyzeResult, error) {
	fmt.Printf("\n--- [模块2] 全站分析启动 (初始URL: %s) ---\n", startURL)

	client := &http.Client{
		Timeout: 15 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return nil // 跟随所有重定向
		},
	}

	req, _ := http.NewRequest("GET", startURL, nil)
	req.Header.Set("User-Agent", userAgent)
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("访问初始URL失败: %w", err)
	}
	defer resp.Body.Close()

	finalURL := resp.Request.URL.String()
	fmt.Printf("[分析] 最终着陆页: %s\n", finalURL)

	baseDomain := resp.Request.URL.Hostname()
	toVisit := []string{finalURL}
	visited := make(map[string]bool)
	var gaPages []string

	for len(toVisit) > 0 {
		currentURL := toVisit[0]
		toVisit = toVisit[1:]
		if visited[currentURL] {
			continue
		}
		visited[currentURL] = true

		fmt.Printf("[分析] 正在爬取: %s\n", currentURL)

		pageResp, err := client.Get(currentURL) // 使用简单的Get请求
		if err != nil {
			log.Printf("[警告] 爬取%s失败: %v\n", currentURL, err)
			continue
		}

		if pageResp.StatusCode != http.StatusOK {
			pageResp.Body.Close()
			continue
		}

		doc, err := goquery.NewDocumentFromReader(pageResp.Body)
		pageResp.Body.Close()
		if err != nil {
			continue
		}

		html, _ := doc.Html()
		if strings.Contains(html, "gtag.js") || strings.Contains(html, "googletagmanager.com") {
			fmt.Println("  -> ✓ 发现GA标记")
			gaPages = append(gaPages, currentURL)
		}

		doc.Find("a").Each(func(i int, s *goquery.Selection) {
			href, _ := s.Attr("href")
			absURL, err := resp.Request.URL.Parse(href)
			if err != nil {
				return
			}

			nextURL := absURL.String()

			if strings.Contains(absURL.Hostname(), baseDomain) && !visited[nextURL] {
				toVisit = append(toVisit, nextURL)
			}
		})
	}

	fmt.Printf("[分析] 分析完成，共分析 %d 页面，发现 %d 个页面有GA标记。\n", len(visited), len(gaPages))
	return &AnalyzeResult{FinalURL: finalURL, GAPages: gaPages}, nil
}

// =================================================================
// 模块 3: GA 流量模拟
// =================================================================
// 注意：这部分代码目前是简化的占位符，你需要用之前我们写好的完整GA模拟代码来替换。

type UserProfile struct {
	UA       string
	Headers  map[string]string
	UAParams map[string]string
}

var userProfiles = []UserProfile{ /* ... 省略具体内容 ... */ }

type GASimulationConfig struct {
	TID         string
	GTM         string
	TargetPages []string
	NumSessions int
}

func simulateGASessions(config GASimulationConfig) {
	fmt.Printf("\n--- [模块3] GA流量模拟启动 (目标: %d个GA页面) ---\n", len(config.TargetPages))
	// 这是一个简化的模拟逻辑
	for i := 0; i < config.NumSessions; i++ {
		fmt.Printf("\n--- [流量] 会话 %d/%d 开始 ---\n", i+1, config.NumSessions)
		// 在这里你需要调用完整的 sendGAHit 逻辑
		log.Printf("  -> (模拟) 向 %s 发送 page_view 事件\n", config.TargetPages[0])
		time.Sleep(1 * time.Second)
	}
}

// =================================================================
// 主程序入口
// =================================================================

//	func main() {
//		//coltest.Test()
//		rand.Seed(time.Now().UnixNano())
//
//		// --- 步骤 1: Google 搜索 ---
//		log.Println("--- 任务开始 ---")
//		query := "ad斗篷"
//		targetDomain := "adcloaking.com" // ✅ 确保定义
//		tld := "com"
//		lang := "lang_zh-CN"
//
//		config := gosearch.SearchClientConfig{
//			Query:      query,
//			Tld:        tld,
//			LangHtmlUI: "zh-CN",
//			LangResult: lang,
//			Verbosity:  true,
//			Num:        100,
//		}
//
//		searcher, err := gosearch.NewSearchClient(config)
//		if err != nil {
//			log.Fatalf("创建客户端失败: %v", err)
//		}
//
//		results, err := searcher.Search()
//		if err != nil {
//			log.Fatalf("[致命错误] 模块1失败: %v", err)
//		}
//
//		var foundURL string
//		for _, res := range results {
//			if url, ok := res.(string); ok {
//				if strings.Contains(url, targetDomain) { // ✅ 使用前必须定义
//					foundURL = url
//					break
//				}
//			}
//		}
//
//		if foundURL == "" {
//			log.Println("[完成] 未在搜索结果中找到目标URL，程序结束。")
//			return
//		}
//		log.Printf("[模块1] ✓ 成功找到目标URL: %s", foundURL)
//
//		// --- 步骤 2: 网站分析 ---
//		analysisResult, err := analyzeSite(foundURL, userProfiles[0].UA)
//		if err != nil {
//			log.Fatalf("[致命错误] 模块2失败: %v", err)
//		}
//
//		if len(analysisResult.GAPages) == 0 {
//			log.Println("[完成] 未发现任何带有GA标记的页面，程序结束。")
//			return
//		}
//
//		// --- 步骤 3: GA 流量模拟 ---
//		gaConfig := GASimulationConfig{
//			TID:         "G-YOUR-TID", // 替换成你的TID
//			GTM:         "YOUR-GTM",   // 替换成你的GTM
//			TargetPages: analysisResult.GAPages,
//			NumSessions: 2,
//		}
//		simulateGASessions(gaConfig)
//
//		log.Println("\n--- 所有模块执行完毕 ---")
//	}
//func main() {
//	config := gosearch.SearchClientConfig{
//		Query:                       "colly framework",
//		MaxSearchResultUrlsToReturn: 50,
//		Num:                         100, // 每次请求100个结果
//		LangHtmlUI:                  "en",
//		UserAgent:                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
//		Verbosity:                   true,
//		// 配置Colly的并行和延迟
//		Parallelism: 2,
//		RandomDelay: 5 * time.Second,
//		// 配置代理列表
//		// Proxies: []string{
//		// 	"socks5://127.0.0.1:1337",
//		// 	"socks5://127.0.0.1:1338",
//		// },
//		// 配置429处理
//		YagooglesearchManagesHttp429s: true,
//		Http429CoolOffTimeInMinutes:   10,
//	}
//
//	client, err := gosearch.NewSearchClient(config)
//	if err != nil {
//		log.Fatalf("Failed to create client: %v", err)
//	}
//
//	results, err := client.Search()
//	if err != nil {
//		log.Fatalf("Search returned an error: %v", err)
//	}
//
//	fmt.Printf("\n--- Found %d results ---\n", len(results))
//	for i, res := range results {
//		fmt.Printf("%d. %s\n", i+1, res)
//	}
//}

// in main.go
func main() {
	log.Println("--- 任务开始 ---")
	query := "ad斗篷"
	tld := "com"
	lang := "lang_zh-CN"

	config := gosearch.SearchClientConfig{
		Query:      query,
		Tld:        tld,
		LangHtmlUI: "zh-CN",
		LangResult: lang,
		Verbosity:  true,
		Num:        100,
	}
	//
	//config := gosearch.SearchClientConfig{
	//	Query:                       "colly framework",
	//	MaxSearchResultUrlsToReturn: 50,
	//	Num:                         100, // 每次请求100个结果
	//	LangHtmlUI:                  "en",
	//	UserAgent:                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36",
	//	Verbosity:                   true,
	//	Parallelism:                 2,
	//	RandomDelay:                 5 * time.Second,
	//}

	client, err := gosearch.NewSearchClient(config)
	if err != nil {
		log.Fatalf("Failed to create client: %v", err)
	}

	// 现在，这个调用会阻塞，直到搜索真正完成
	results, err := client.Search()
	if err != nil {
		log.Fatalf("Search returned an error: %v", err)
	}

	// 这段代码现在只有在搜索完成后才会执行
	fmt.Printf("\n--- Found %d results ---\n", len(results))
	for i, res := range results {
		fmt.Printf("%d. %s\n", i+1, res)
	}
}
