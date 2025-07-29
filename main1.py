package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"github.com/PuerkitoBio/goquery"
	"github.com/gocolly/colly"
	"github.com/gocolly/colly/debug"
	"github.com/gocolly/colly/extensions"
	"log"
	"math/rand"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// =================================================================
// 1. 配置和结构体定义
// =================================================================

type AppConfig struct {
	Query                string
	TargetDomain         string
	Tld                  string
	Proxy                string
	SearchDelay          time.Duration
	CrawlDelay           time.Duration
	Parallelism          int
	TID                  string
	GTM                  string
	NumSessions          int
	YesCaptchaToken      string
	CustomRequestHeaders map[string]string
}

// YesCaptcha API响应结构体
type CreateTaskResponse struct {
	ErrorID          int    `json:"errorId"`
	ErrorCode        string `json:"errorCode"`
	ErrorDescription string `json:"errorDescription"`
	TaskID           string `json:"taskId"`
}

type GetTaskResultResponse struct {
	ErrorID          int    `json:"errorId"`
	ErrorCode        string `json:"errorCode"`
	ErrorDescription string `json:"errorDescription"`
	Status           string `json:"status"`
	Solution         struct {
		GRecaptchaResponse string `json:"gRecaptchaResponse"`
	} `json:"solution"`
}

// =================================================================
// 2. 模块定义
// =================================================================

// --- 模块1: 会话预热 ---
func runModule1_WarmUp(baseCollector *colly.Collector, cfg *AppConfig) error {
	log.Println("--- [模块1] 会话预热启动 ---")
	c1 := baseCollector.Clone()
	preheatURL := fmt.Sprintf("https://www.google.%s/", cfg.Tld)

	err := c1.Visit(preheatURL)
	if err != nil {
		return fmt.Errorf("访问Google首页失败: %w", err)
	}
	c1.Wait()

	cookies := c1.Cookies(preheatURL)
	if len(cookies) == 0 {
		log.Println("[警告] 预热后未获取到任何Cookie。")
	} else {
		log.Printf("[模块1] 预热成功, 获取到 %d 个Cookie。", len(cookies))
		baseCollector.SetCookies(preheatURL, cookies)
	}
	return nil
}

// --- 模块2: 谷歌搜索 (OnResponse为核心，手动解析) ---
var errCaptchaRequired = fmt.Errorf("captcha required")

type SearchResult struct {
	TargetURL  string
	CaptchaURL string
	IsCaptcha  bool
}

func runModule2_Search(baseCollector *colly.Collector, cfg *AppConfig) (*SearchResult, error) {
	log.Println("--- [模块2] 谷歌搜索启动 (OnResponse核心模式) ---")

	finalResult := &SearchResult{}
	var finalErr error

	// 使用一个WaitGroup来确保所有异步操作都完成
	var wg sync.WaitGroup

	c2 := baseCollector.Clone()
	c2.Limit(&colly.LimitRule{ /* ... */ })

	// 【核心逻辑】所有判断都在OnResponse中完成
	c2.OnResponse(func(r *colly.Response) {
		// 检查是否是验证码页面
		if bytes.Contains(r.Body, []byte("g-recaptcha")) || bytes.Contains(r.Body, []byte("/sorry/")) {
			log.Printf("[模块2] 在 OnResponse 中检测到验证码页面内容! URL: %s", r.Request.URL.String())
			finalResult.IsCaptcha = true
			finalResult.CaptchaURL = r.Request.URL.String()
			return // 是验证码页面，直接返回，不再解析
		}

		// --- 如果不是验证码，就手动解析HTML ---
		log.Printf("[模块2] 在 OnResponse 中处理正常页面: %s", r.Request.URL.String())

		doc, err := goquery.NewDocumentFromReader(bytes.NewReader(r.Body))
		if err != nil {
			log.Printf("[错误] 手动解析HTML失败: %v", err)
			finalErr = err
			return
		}

		// 1. 查找目标链接
		if finalResult.TargetURL == "" { // 确保只找一次
			doc.Find("a[href]").EachWithBreak(func(i int, s *goquery.Selection) bool {
				href, _ := s.Attr("href")
				if strings.Contains(href, cfg.TargetDomain) {
					finalURL := r.Request.AbsoluteURL(href)
					if strings.HasPrefix(finalURL, "https://www.google.com/url?q=") {
						parsed, _ := url.Parse(finalURL)
						finalURL = parsed.Query().Get("q")
					}
					log.Printf("--- [模块2] 在 OnResponse 中找到目标URL: %s ---", finalURL)
					finalResult.TargetURL = finalURL
					return false // 找到后停止 дальнейший поиск (break)
				}
				return true // 继续查找
			})
		}

		// 2. 如果还没找到目标，查找并访问翻页链接
		if finalResult.TargetURL == "" {
			nextPage, exists := doc.Find("#pnnext").Attr("href")
			if exists {
				nextPageURL := r.Request.AbsoluteURL(nextPage)
				log.Printf("[模块2] 发现翻页链接，准备访问: %s", nextPageURL)

				// 增加WaitGroup计数，并发起新的访问
				wg.Add(1)
				go func() {
					defer wg.Done()
					r.Request.Visit(nextPageURL)
				}()
			}
		}
	})

	c2.OnError(func(r *colly.Response, err error) {
		log.Printf("[模块2] 请求出错: %v, URL: %s", err, r.Request.URL)
		finalErr = err
	})

	searchURL := fmt.Sprintf("https://www.google.%s/search?q=%s&num=100&hl=en", cfg.Tld, url.QueryEscape(cfg.Query))

	// 初始访问也加入WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		c2.Visit(searchURL)
	}()

	// 等待所有访问（初始+翻页）完成
	wg.Wait()

	log.Println("--- [模块2] 所有搜索任务执行完毕 ---")

	// 根据最终收集到的结果返回
	if finalResult.TargetURL != "" {
		return finalResult, nil
	}
	if finalResult.IsCaptcha {
		return finalResult, errCaptchaRequired
	}
	if finalErr != nil {
		return nil, finalErr
	}

	return finalResult, fmt.Errorf("搜索完成，但未能找到目标URL")
}

// --- 模块3: 验证码解决 (Colly驱动) ---
func runModule3_SolveCaptcha(baseCollector *colly.Collector, captchaURL string, cfg *AppConfig) error {
	log.Println("--- [模块3] 验证码解决启动 (Colly驱动) ---")

	var sitekey, gRecaptchaResponse, qValue string
	var solveError error
	solveDone := make(chan struct{})

	c3 := baseCollector.Clone()

	// 设置一个较长的超时时间，因为打码需要等待
	c3.SetRequestTimeout(150 * time.Second)

	c3.OnHTML(".g-recaptcha", func(e *colly.HTMLElement) {
		sitekey = e.Attr("data-sitekey")
	})
	c3.OnHTML("input[name=q]", func(e *colly.HTMLElement) {
		qValue = e.Attr("value")
	})

	c3.OnScraped(func(r *colly.Response) {
		// 确保只在访问验证码页面后触发
		if r.Request.URL.String() != captchaURL {
			return
		}
		if sitekey == "" {
			solveError = fmt.Errorf("未能从验证码页面提取到sitekey")
			close(solveDone)
			return
		}
		log.Printf("[打码] 成功提取到 sitekey: %s", sitekey)

		createTaskPayload := map[string]interface{}{
			"clientKey": cfg.YesCaptchaToken,
			"task":      map[string]string{"type": "NoCaptchaTaskProxyless", "websiteURL": captchaURL, "websiteKey": sitekey},
		}
		payloadBytes, _ := json.Marshal(createTaskPayload)
		c3.PostRaw("https://api.yescaptcha.com/createTask", payloadBytes)
	})

	c3.OnResponse(func(r *colly.Response) {
		requestURL := r.Request.URL.String()

		if strings.Contains(requestURL, "createTask") {
			var resp CreateTaskResponse
			if err := json.Unmarshal(r.Body, &resp); err != nil {
				solveError = fmt.Errorf("解析createTask响应失败: %v", err)
				close(solveDone)
				return
			}
			if resp.ErrorID != 0 {
				solveError = fmt.Errorf("创建打码任务返回错误: %s", resp.ErrorCode)
				close(solveDone)
				return
			}
			taskId := resp.TaskID
			log.Printf("[打码] 任务创建成功, TaskID: %s。开始轮询...", taskId)

			go func() {
				ticker := time.NewTicker(3 * time.Second)
				defer ticker.Stop()
				timeout := time.After(120 * time.Second)
				for {
					select {
					case <-ticker.C:
						resultPayload := map[string]string{"clientKey": cfg.YesCaptchaToken, "taskId": taskId}
						payloadBytes, _ := json.Marshal(resultPayload)
						c3.PostRaw("https://api.yescaptcha.com/getTaskResult", payloadBytes)
					case <-timeout:
						solveError = fmt.Errorf("打码超时")
						close(solveDone)
						return
					case <-solveDone:
						return
					}
				}
			}()

		} else if strings.Contains(requestURL, "getTaskResult") {
			var resp GetTaskResultResponse
			if err := json.Unmarshal(r.Body, &resp); err != nil {
				log.Printf("[警告] 解析getTaskResult响应失败: %v", err)
				return
			}
			if resp.Status == "ready" {
				gRecaptchaResponse = resp.Solution.GRecaptchaResponse
				log.Printf("[打码] 成功获取到 gRecaptchaResponse token!")

				formData := map[string]string{"g-recaptcha-response": gRecaptchaResponse, "q": qValue}
				c3.Post("https://www.google.com/sorry/index", formData)
			}

		} else if strings.Contains(requestURL, "/sorry/index") {
			log.Printf("[会话同步] 验证提交成功! 状态码: %d", r.StatusCode)
			googleURL, _ := url.Parse("https://www.google.com/")
			newCookies := c3.Cookies(googleURL.String())
			if len(newCookies) > 0 {
				log.Printf("[会话同步] 捕获 %d 个已验证的Cookie，同步回母版...", len(newCookies))
				baseCollector.SetCookies(googleURL.String(), newCookies)
			} else {
				solveError = fmt.Errorf("提交验证后未能捕获到新的Cookie")
			}
			close(solveDone)
		}
	})

	c3.Visit(captchaURL)
	<-solveDone // 等待整个异步流程完成或出错

	return solveError
}

// --- 模块4 & 5 (占位符) ---
func runModule4_Analyze(baseCollector *colly.Collector, startURL string, cfg *AppConfig) ([]string, error) {
	log.Println("--- [模块4] 全站分析启动 ---")
	return []string{startURL}, nil
}
func runModule5_Simulate(gaPages []string, cfg *AppConfig) error {
	log.Println("--- [模块5] GA流量模拟启动 ---")
	return nil
}

// =================================================================
// 3. 主工作流
// =================================================================
func main() {
	rand.Seed(time.Now().UnixNano())

	config := &AppConfig{
		Query:                "ad斗篷",
		TargetDomain:         "adcloaking.com",
		Tld:                  "com.hk",
		Proxy:                "http://127.0.0.1:8080",
		SearchDelay:          5 * time.Second,
		CrawlDelay:           500 * time.Millisecond,
		Parallelism:          1,
		YesCaptchaToken:      "YOUR_YESCAPTCHA_TOKEN", // <--- 在这里替换你的TOKEN
		CustomRequestHeaders: map[string]string{},
	}

	baseCollector := colly.NewCollector(
		colly.Async(true),
		colly.Debugger(&debug.LogDebugger{}),
		colly.AllowURLRevisit(),
	)
	extensions.RandomUserAgent(baseCollector)
	extensions.Referer(baseCollector)

	if config.Proxy != "" {
		proxyURL, _ := url.Parse(config.Proxy)
		baseCollector.SetProxyFunc(http.ProxyURL(proxyURL))
		baseCollector.WithTransport(&http.Transport{
			Proxy:           http.ProxyURL(proxyURL),
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		})
	}

	baseCollector.OnRequest(func(r *colly.Request) {
		r.Headers.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
		r.Headers.Set("Accept-Language", "en-US,en;q=0.9,zh-CN;q=0.8")
		if strings.Contains(r.URL.Host, "yescaptcha.com") {
			r.Headers.Set("Content-Type", "application/json")
		}
		for key, value := range config.CustomRequestHeaders {
			r.Headers.Set(key, value)
		}
	})

	log.Println("=============== 流程开始，执行 Plan A ===============")

	if err := runModule1_WarmUp(baseCollector, config); err != nil {
		log.Fatalf("[致命错误] 模块1 (预热) 失败: %v", err)
	}

	// --- 模块2: 搜索 ---
	searchResult, err := runModule2_Search(baseCollector, config)

	// --- 决策点: 根据模块2的结果决定下一步 ---
	if searchResult.TargetURL != "" {
		// Plan A 成功
		log.Println("=============== Plan A 成功！继续后续流程 ===============")
		// ... 调用模块4/5 ...

		gaPages, err := runModule4_Analyze(baseCollector, "", config)
		if err != nil {
			log.Fatalf("[致命错误] 模块4 (分析) 失败: %v", err)
		}

		if err := runModule5_Simulate(gaPages, config); err != nil {
			log.Fatalf("[致命错误] 模块5 (模拟) 失败: %v", err)
		}

		log.Println("\n🎉🎉🎉 所有模块成功执行完毕! 🎉🎉🎉")
	} else if err == errCaptchaRequired {
		// Plan A 失败, 切换到 Plan B
		log.Println("=============== Plan A 失败, 启动 Plan B (验证码解决流程) ===============")

		if solveErr := runModule3_SolveCaptcha(baseCollector, searchResult.CaptchaURL, config); solveErr != nil {
			log.Fatalf("[致命错误] 验证码解决失败: %v", solveErr)
		}

		log.Println("=============== Plan B 执行成功! 会话已解锁，重新尝试搜索 ===============")

		// 再次执行模块2
		finalSearchResult, finalErr := runModule2_Search(baseCollector, config)
		if finalErr != nil || finalSearchResult.TargetURL == "" {
			log.Fatalf("[致命错误] 解决验证码后，再次搜索仍然失败: %v", finalErr)
		}

		log.Println("=============== 再次搜索成功！继续后续流程 ===============")

		gaPages, err := runModule4_Analyze(baseCollector, "", config)
		if err != nil {
			log.Fatalf("[致命错误] 模块4 (分析) 失败: %v", err)
		}

		if err := runModule5_Simulate(gaPages, config); err != nil {
			log.Fatalf("[致命错误] 模块5 (模拟) 失败: %v", err)
		}

		log.Println("\n🎉🎉🎉 所有模块成功执行完毕! 🎉🎉🎉")
	} else {
		// 其他错误，或正常结束但没找到
		log.Fatalf("[流程终止] 搜索结束，但未找到目标URL或遇到未知错误: %v", err)
	}

}
