// 文件: main.go
package main

import (
	"encoding/json"
	"fmt"
	"github.com/gocolly/colly"
	"log"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
)

type SearchResult struct {
	Rank    int    `json:"rank"`
	URL     string `json:"url"`
	Title   string `json:"title"`
	Snippet string `json:"snippet"`
}

type GooglePageData struct {
	EI           string
	PSI          string
	OPI          string
	BL           string
	VED          string
	JSController string
	Iflsig       string
	Sclient      string
	// 新增字段，用于存储从搜索结果页提取的新参数
	NextEI       string
	NextSEI      string
	NextOPI      string
	NextBL       string
	ClickCounter int
}

var gCheckRegex = regexp.MustCompile(`var\s*_g\s*=\s*\{`)

// 完美版的 setHeaders 函数 (更健壮的Cookie处理版本)
func setHeaders(c *colly.Collector, r *colly.Request, headers map[string]string) {
	// 1. 从Cookie Jar获取Cookies

	cookies := c.Cookies(r.URL.Host)
	// 2. 彻底重置请求头
	r.Headers = &http.Header{}

	// 3. 设置我们自定义的头
	for key, value := range headers {
		r.Headers.Set(key, value)
	}

	// 4. 手动重建 Cookie 请求头
	if len(cookies) > 0 {
		var cookieStrings []string
		for _, cookie := range cookies {
			cookieStrings = append(cookieStrings, cookie.Name+"="+cookie.Value)
		}
		// 将所有cookie拼接成一个单一的、用分号分隔的字符串，这是最标准的做法
		r.Headers.Set("Cookie", strings.Join(cookieStrings, "; "))
	}
}
func main() {
	// =======================================================
	//               ** 核心修改：初始化JS执行器 **
	// =======================================================
	log.Println("--- 流程0: 初始化JS执行环境 ---")
	jsExecutor, err := NewJsExecutor()
	if err != nil {
		log.Fatalf("无法初始化JS执行器: %v", err)
	}
	log.Println("  > JS执行器已准备就绪。")

	searchTerm := "跟换" // 使用您素材中的搜索词
	var finalResults []SearchResult
	var pageData GooglePageData
	rand.Seed(time.Now().UnixNano())

	// --- 创建所有需要的 Collector ---
	baseC := colly.NewCollector() // 基础Collector，其他都从它克隆

	// 1. 访问首页的 Collector
	initC := baseC.Clone()
	// 2. 加载JS文件的 Collector
	xjsC := baseC.Clone()
	// 3. 各种 gen_204 信标的 Collector
	gen204InteractionC := baseC.Clone() // 模拟点击/打字的交互信标
	gen204ErrorC := baseC.Clone()       // 模拟脚本错误上报
	gen204PerfC := baseC.Clone()        // 模拟性能上报
	// 4. 搜索相关的 Collector
	searchC := baseC.Clone()
	// 5. 搜索后资源加载的 Collector
	pageAdC := baseC.Clone()
	verifyC := baseC.Clone()
	imageC := baseC.Clone()
	searchC.OnResponse(func(r *colly.Response) {
		// 4. 在回调函数中，检查 Context 中是否有我们设置的标记
		if r.Request.Ctx.Get("request_stage") == "first_search_response" {
			log.Println("  > 捕获到第一次搜索的响应，准备发起最终搜索请求...")

			// --- 这里是您之前写在临时回调里的逻辑 ---
			parsedURL, _ := url.Parse(r.Request.URL.String())
			newParams := parsedURL.Query()
			// 使用您日志中的sei
			newParams.Add("sei", "-A2LaIfNJeHk1e8P78mm4QE")

			finalURL := "https://www.google.com/search?" + newParams.Encode()

			// 为最终搜索请求创建并设置新的Context
			finalCtx := colly.NewContext()
			// 设置第二次搜索的Referer
			finalCtx.Put("Referer", r.Request.URL.String())
			searchC.Request("GET", finalURL, nil, finalCtx, nil)
			// --- 逻辑结束 ---

		} else {
			// 这是处理最终搜索请求或其他请求的响应的地方
			log.Printf("最终搜索请求的状态码: %d", r.StatusCode)
			err := os.WriteFile("final_response.html", r.Body, 0644)
			if err != nil {
				log.Fatalf("保存HTML文件失败: %v", err)
			}
			log.Println("✅ 最终响应已保存到 final_response.html 文件中。")
		}
	})

	gen204InteractionC.OnRequest(func(r *colly.Request) {
		setHeaders(gen204InteractionC, r, map[string]string{
			"Pragma":                      "no-cache",
			"Cache-Control":               "no-cache",
			"Downlink":                    "10",
			"Sec-Ch-Ua-Full-Version-List": `"Not)A;Brand";v="8.0.0.0", "Chromium";v="138.0.7204.169", "Microsoft Edge";v="138.0.3351.109"`,
			"Sec-Ch-Ua-Platform":          `"Windows"`,
			"Sec-Ch-Ua":                   `"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"`,
			"Sec-Ch-Ua-Bitness":           `"64"`,
			"Sec-Ch-Ua-Model":             `""`,
			"Sec-Ch-Ua-Mobile":            "?0",
			"Sec-Ch-Ua-Form-Factors":      `"Desktop"`,
			"Sec-Ch-Ua-Wow64":             "?0",
			"Sec-Ch-Ua-Arch":              `"x86"`,
			"Sec-Ch-Ua-Full-Version":      `"138.0.3351.109"`,
			"Sec-Ch-Prefers-Color-Scheme": "light",
			"User-Agent":                  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
			"Rtt":                         "0",
			"Sec-Ch-Ua-Platform-Version":  `"10.0.0"`,
			"Accept":                      "*/*",
			"Origin":                      "https://www.google.com",
			"Sec-Fetch-Site":              "same-origin",
			"Sec-Fetch-Mode":              "no-cors",
			"Sec-Fetch-Dest":              "empty",
			"Referer":                     "https://www.google.com/",
			"Accept-Encoding":             "gzip, deflate, br",
			"Accept-Language":             "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
			"Priority":                    "u=4, i",
		})
	})
	initC.OnRequest(func(r *colly.Request) {
		// 调用 setHeaders，并传入根据新素材精确构建的 map
		setHeaders(initC, r, map[string]string{
			"Pragma":                      "no-cache",
			"Cache-Control":               "no-cache",
			"Rtt":                         "0",
			"Downlink":                    "10",
			"Sec-Ch-Ua":                   `"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"`,
			"Sec-Ch-Ua-Mobile":            "?0",
			"Sec-Ch-Ua-Full-Version":      `"138.0.3351.109"`,
			"Sec-Ch-Ua-Arch":              `"x86"`,
			"Sec-Ch-Ua-Platform":          `"Windows"`,
			"Sec-Ch-Ua-Platform-Version":  `"10.0.0"`,
			"Sec-Ch-Ua-Model":             `""`,
			"Sec-Ch-Ua-Bitness":           `"64"`,
			"Sec-Ch-Ua-Wow64":             "?0",
			"Sec-Ch-Ua-Full-Version-List": `"Not)A;Brand";v="8.0.0.0", "Chromium";v="138.0.7204.169", "Microsoft Edge";v="138.0.3351.109"`,
			"Sec-Ch-Ua-Form-Factors":      `"Desktop"`,
			"Sec-Ch-Prefers-Color-Scheme": "light",
			"Upgrade-Insecure-Requests":   "1",
			"User-Agent":                  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
			"Accept":                      "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
			"Sec-Fetch-Site":              "none",     // 注意这里的变化
			"Sec-Fetch-Mode":              "navigate", // 注意这里的变化
			"Sec-Fetch-User":              "?1",
			"Sec-Fetch-Dest":              "document", // 注意这里的变化
			"Accept-Encoding":             "gzip, deflate, br",
			"Accept-Language":             "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
			"Priority":                    "u=0, i", // 注意这里的变化
			// "Referer" 头已被移除，因为 Sec-Fetch-Site 是 none
		})
	})
	xjsC.OnRequest(func(r *colly.Request) {
		setHeaders(xjsC, r, map[string]string{
			"Pragma":                      "no-cache",
			"Cache-Control":               "no-cache",
			"Downlink":                    "10",
			"Sec-Ch-Ua-Full-Version-List": `"Not)A;Brand";v="8.0.0.0", "Chromium";v="138.0.7204.169", "Microsoft Edge";v="138.0.3351.109"`,
			"Sec-Ch-Ua-Platform":          `"Windows"`,
			"Sec-Ch-Ua":                   `"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"`,
			"Sec-Ch-Ua-Bitness":           `"64"`,
			"Sec-Ch-Ua-Model":             `""`,
			"Sec-Ch-Ua-Mobile":            "?0",
			"Sec-Ch-Ua-Form-Factors":      `"Desktop"`,
			"Sec-Ch-Ua-Wow64":             "?0",
			"Sec-Ch-Ua-Arch":              `"x86"`,
			"Sec-Ch-Ua-Full-Version":      `"138.0.3351.109"`,
			"Sec-Ch-Prefers-Color-Scheme": "light",
			"User-Agent":                  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
			"Rtt":                         "0",
			"Sec-Ch-Ua-Platform-Version":  `"10.0.0"`,
			"Accept":                      "*/*",
			"Sec-Fetch-Site":              "same-origin",
			"Sec-Fetch-Mode":              "no-cors",
			//"Sec-Fetch-Dest":              "script",//对资源的类型后续做修改
			"Referer":         "https://www.google.com/",
			"Accept-Encoding": "gzip, deflate, br",
			"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
			"Priority":        "u=1",
		})
	})
	searchC.OnRequest(func(r *colly.Request) {
		setHeaders(searchC, r, map[string]string{
			"Pragma":                      "no-cache",
			"Cache-Control":               "no-cache",
			"Rtt":                         "0",
			"Downlink":                    "10",
			"Sec-Ch-Ua":                   `"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"`,
			"Sec-Ch-Ua-Mobile":            "?0",
			"Sec-Ch-Ua-Full-Version":      `"138.0.3351.109"`,
			"Sec-Ch-Ua-Arch":              `"x86"`,
			"Sec-Ch-Ua-Platform":          `"Windows"`,
			"Sec-Ch-Ua-Platform-Version":  `"10.0.0"`,
			"Sec-Ch-Ua-Model":             `""`,
			"Sec-Ch-Ua-Bitness":           `"64"`,
			"Sec-Ch-Ua-Wow64":             "?0",
			"Sec-Ch-Ua-Full-Version-List": `"Not)A;Brand";v="8.0.0.0", "Chromium";v="138.0.7204.169", "Microsoft Edge";v="138.0.3351.109"`,
			"Sec-Ch-Ua-Form-Factors":      `"Desktop"`,
			"Sec-Ch-Prefers-Color-Scheme": "light",
			"Upgrade-Insecure-Requests":   "1",
			"User-Agent":                  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
			"Accept":                      "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
			"Sec-Fetch-Site":              "same-origin",
			"Sec-Fetch-Mode":              "navigate",
			"Sec-Fetch-Dest":              "document",
			"Referer":                     r.Ctx.Get("Referer"), // Referer是动态的！
			"Accept-Encoding":             "gzip, deflate, br",
			"Accept-Language":             "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
			"Priority":                    "u=0, i",
		})
	})
	gen204ErrorC.OnRequest(func(r *colly.Request) {
		setHeaders(gen204ErrorC, r, map[string]string{
			"Pragma":                      "no-cache",
			"Cache-Control":               "no-cache",
			"Downlink":                    "10",
			"Sec-Ch-Ua-Full-Version-List": `"Not)A;Brand";v="8.0.0.0", "Chromium";v="138.0.7204.169", "Microsoft Edge";v="138.0.3351.109"`,
			"Sec-Ch-Ua-Platform":          `"Windows"`,
			"Sec-Ch-Ua":                   `"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"`,
			// ... 省略其他不变的 Sec-Ch-* 和 UA 头 ...
			"User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
			"Rtt":             "0",
			"Accept":          "*/*",
			"Origin":          "https://www.google.com",
			"Sec-Fetch-Site":  "same-origin",
			"Sec-Fetch-Mode":  "no-cors",
			"Sec-Fetch-Dest":  "empty",
			"Referer":         r.Ctx.Get("Referer"), // Referer是动态的！
			"Accept-Encoding": "gzip, deflate, br",
			"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
			"Priority":        "u=4, i",
		})
	})
	pageAdC.OnRequest(func(r *colly.Request) {
		setHeaders(pageAdC, r, map[string]string{
			// ... 根据 #5 的素材填充所有头 ...
			"Accept":         "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
			"Sec-Fetch-Dest": "image",
			"Priority":       "i",
			"Referer":        r.Ctx.Get("Referer"),
			// ... 其他头 ...
		})
	})
	verifyC.OnRequest(func(r *colly.Request) {
		setHeaders(verifyC, r, map[string]string{
			// ... 根据 #5 的素材填充所有头 ...
			"Accept":         "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
			"Sec-Fetch-Dest": "image",
			"Priority":       "i",
			"Referer":        r.Ctx.Get("Referer"),
			// ... 其他头 ...
		})
	})
	imageC.OnRequest(func(r *colly.Request) {
		setHeaders(imageC, r, map[string]string{
			// ... 根据 #5 的素材填充所有头 ...
			"Accept":         "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
			"Sec-Fetch-Dest": "image",
			"Priority":       "i",
			"Referer":        r.Ctx.Get("Referer"),
			// ... 其他头 ...
		})
	})
	gen204PerfC.OnRequest(func(r *colly.Request) {
		setHeaders(gen204PerfC, r, map[string]string{
			// ... 根据 #5 的素材填充所有头 ...
			"Accept":         "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
			"Sec-Fetch-Dest": "image",
			"Priority":       "i",
			"Referer":        r.Ctx.Get("Referer"),
			// ... 其他头 ...
		})
	})

	initC.OnHTML("input[name=ei]", func(e *colly.HTMLElement) {
		pageData.EI = e.Attr("value")
		pageData.PSI = e.Attr("value")
	})
	initC.OnHTML("input[name=iflsig]", func(e *colly.HTMLElement) { pageData.Iflsig = e.Attr("value") })
	initC.OnHTML("APjFqb", func(e *colly.HTMLElement) {
		pageData.VED = e.Attr("data-ved")
	})
	initC.OnHTML("div[jscontroller][jsname=gLFyf]", func(e *colly.HTMLElement) { pageData.JSController = e.Attr("jscontroller") })
	initC.OnHTML("form[action='/search']", func(e *colly.HTMLElement) {
		sclientVal := e.ChildAttr("input[name=sclient]", "value")
		if sclientVal == "" {
			sclientVal = "gws-wiz"
		}
		pageData.Sclient = sclientVal
	})
	initC.OnHTML("script", func(e *colly.HTMLElement) {
		if jsSrc := e.Attr("src"); jsSrc != "" {
			jsURL := e.Request.AbsoluteURL(jsSrc)
			log.Printf("[initC] 发现并访问外部JS文件: %s", jsURL)
			xjsC.Visit(jsURL)
			return
		}

		scriptContent := e.Text
		if !gCheckRegex.MatchString(scriptContent) {
			return
		}
		log.Println("[JS提取] 定位到包含 `_g` 对象的关键<script>，开始解析...")
		reOPI := regexp.MustCompile(`kOPI:\s*(\d+)`)
		if m := reOPI.FindStringSubmatch(scriptContent); len(m) > 1 {
			pageData.OPI = m[1]
		}
		reBL := regexp.MustCompile(`kBL:\s*'([^']+)'`)
		if m := reBL.FindStringSubmatch(scriptContent); len(m) > 1 {
			pageData.BL = m[1]
		}
		reEI := regexp.MustCompile(`kEI:\s*'([^']+)'`)
		if m := reEI.FindStringSubmatch(scriptContent); len(m) > 1 && pageData.EI == "" {
			pageData.EI = m[1]
		}
	})

	initC.OnScraped(func(r *colly.Response) {
		// 这是处理最终搜索请求或其他请求的响应的地方
		log.Printf("最终搜索请求的状态码: %d", r.StatusCode)
		err := os.WriteFile("google.html", r.Body, 0644)
		if err != nil {
			log.Fatalf("保存HTML文件失败: %v", err)
		}
		log.Println("✅ 最终响应已保存到 google.html 文件中。")

		log.Println("[initC] 首页参数提取完成。")
		log.Printf("  > EI: %s, Iflsig: %s, VED: %s, OPI: %s, BL: %s, Sclient: %s",
			pageData.EI, pageData.Iflsig, pageData.VED, pageData.OPI, pageData.BL, pageData.Sclient)

		if pageData.EI == "" || pageData.Iflsig == "" {
			log.Fatal("关键参数EI或iflsig提取失败，流程终止。")
		}

		simulateClickSendGen_204(gen204InteractionC, &pageData)
		simulateTyping(searchC, gen204InteractionC, &pageData, searchTerm)
		// =======================================================
		//               ** 核心修改：在最终搜索前生成gs_lp **
		// =======================================================
		//log.Println("\n--- 流程3.5: 生成gs_lp加密参数 ---")
		//gsLp, err := jsExecutor.GenerateGsLp(searchTerm, &pageData)
		//if err != nil {
		//	log.Printf("  [警告] 生成gs_lp失败: %v。将不带此参数进行搜索。", err)
		//	gsLp = "Egdnd3Mtd2l6IgZzZHNhZGZI1gdQqANYlgVwA3gAkAEDmAH5AaAB8wWqAQUxLjMuMbgBA8gBAPgBAZgCAaACjgGoAgDCAhAQLhiABBjRAxhDGMcBGIoFwgIKEAAYgAQYQxiKBcICDhAuGIAEGNEDGNQCGMcBwgIFEAAYgATCAgsQLhiABBjRAxjHAZgDAfEFRfOusG9HgmOSBwMwLjGgB5slsgcDMC4xuAeOAcIHAzItMcgHAw" // 如果失败，就用固定字符串
		//} else {
		//	log.Printf("  > 成功生成gs_lp: %s", gsLp)
		//}
		log.Println("\n--- 流程3.5: 生成gs_lp加密参数 ---")
		gsLp, err := jsExecutor.GenerateGsLp(searchTerm, &pageData)
		if err != nil {
			log.Printf("  [警告] 生成gs_lp失败: %v", err)
			gsLp = "Egdnd3Mtd2l6IgZzZHNhZGZI1gdQqANYlgVwA3gAkAEDmAH5AaAB8wWqAQUxLjMuMbgBA8gBAPgBAZgCAaACjgGoAgDCAhAQLhiABBjRAxhDGMcBGIoFwgIKEAAYgAQYQxiKBcICDhAuGIAEGNEDGNQCGMcBwgIFEAAYgATCAgsQLhiABBjRAxjHAZgDAfEFRfOusG9HgmOSBwMwLjGgB5slsgcDMC4xuAeOAcIHAzItMcgHAw" // 您的备用gs_lp
		}
		log.Printf("  > 成功生成gs_lp: %s", gsLp)
		// **核心修改**：调用第一次搜索
		executeFirstSearch(searchC, &pageData, searchTerm, gsLp)
	})
	searchC.OnScraped(func(r *colly.Response) {

		log.Println("--- 流程1: 访问主页并提取参数 ---")
	})
	searchC.OnHTML("html", func(e *colly.HTMLElement) {
		// 提取最终结果
		e.ForEach("div.g", func(_ int, el *colly.HTMLElement) {
			if el.ChildText("h3") == "" {
				return
			}
			finalResults = append(finalResults, SearchResult{
				Rank: len(finalResults) + 1, Title: el.ChildText("h3"), URL: el.ChildAttr("a", "href"), Snippet: el.ChildText("div[data-sncf]"),
			})
		})

		// 提取新一轮的参数，用于发送性能信标
		scriptContent := e.ChildText("script[nonce]")
		reEI := regexp.MustCompile(`kEI:\s*'([^']+)'`)
		if m := reEI.FindStringSubmatch(scriptContent); len(m) > 1 {
			pageData.NextEI = m[1]
		}
		// ... 提取其他的如 NextOPI, NextBL ...

		// 2.3 模拟页面加载后的资源请求和信标
		// (这里只做示例，实际URL需要从HTML中用goquery精确提取)
		log.Println("[searchC] 模拟搜索结果页的后续请求...")

		currentURL := e.Request.URL.String()
		ctx := colly.NewContext()
		ctx.Put("Referer", currentURL)

		// 模拟 #5, #6, #7
		go pageAdC.Request("GET", "https://www.google.com/pagead/1p-conversion/...", nil, ctx, nil)
		go verifyC.Request("GET", "https://www.google.com/verify/...", nil, ctx, nil)
		go imageC.Request("GET", "https://www.google.com/images/nav_logo321.webp", nil, ctx, nil)

		// 模拟性能上报信标 (对应您的最后一个请求)
		// 注意: rt参数等是动态计算的，这里用固定值代替，高保真需要模拟计算
		perfBeaconURL := fmt.Sprintf("https://www.google.com/gen_204?s=web&t=aft&atyp=csi&ei=%s&rt=wsrt.604,hst.28&opi=%s",
			pageData.NextEI, pageData.NextOPI)
		go gen204PerfC.Request("POST", perfBeaconURL, nil, ctx, nil)
	})
	// --- 启动流程 ---
	log.Println("--- 流程1: 访问主页并提取参数 ---")
	initC.Visit("https://www.google.com/")
	baseC.Wait() // 等待所有克隆出的Collector完成

	// 等待所有异步任务完成
	initC.Wait()
	xjsC.Wait()
	searchC.Wait()

	// 输出漂亮的JSON
	log.Println("\n✅✅✅ 完整、逼真的搜索流程模拟完毕。✅✅✅")
	jsonData, err := json.MarshalIndent(finalResults, "", "  ")
	if err != nil {
		log.Fatal("JSON格式化失败:", err)
	}
	fmt.Println(string(jsonData))
	os.WriteFile("google_search_results.json", jsonData, 0644)
}

// --- 流程2的辅助函数 ---
func simulateClickSendGen_204(c *colly.Collector, pd *GooglePageData) {
	log.Println("\n--- 流程2: 模拟点击输入框 (发送全套信标) ---")
	//if pd.VED == "" || pd.JSController == "" {
	//	log.Println("  [警告] 缺少VED或JSController，跳过点击信标发送。")
	//	return
	//}
	pd.ClickCounter++
	t1 := rand.Intn(1000)
	jsi := fmt.Sprintf("hd,st.%d,tni.0,atni.1,et.click,n.%s,cn.%d,ie.0,vi.1,fht.%d,naj.%d",
		t1, pd.JSController, pd.ClickCounter, t1+rand.Intn(50), t1+rand.Intn(50)+1)

	csiURL := fmt.Sprintf("https://www.google.com/gen_204?atyp=csi&ei=%s&s=jsa&jsi=%s&zx=%d&opi=%s",
		pd.EI, url.QueryEscape(jsi), time.Now().UnixMilli(), pd.OPI)
	interactionURL := fmt.Sprintf("https://www.google.com/gen_204?atyp=i&ei=%s&ved=%s&bl=%s&s=webhp&zx=%d&opi=%s",
		pd.EI, pd.VED, pd.BL, time.Now().UnixMilli(), pd.OPI)

	log.Println("  发送CSI信标...")
	c.Visit(csiURL)
	log.Println("  发送Interaction信标...")
	c.Visit(interactionURL)
}

// --- 流程3的辅助函数 ---
func simulateTyping(searchC, gen_204C *colly.Collector, pd *GooglePageData, term string) {
	log.Printf("\n--- 流程3: 模拟输入关键词 '%s' ---", term)
	//if pd.PSI == "" {
	//	log.Println("  [警告] 缺少PSI，跳过模拟输入步骤。")
	//	return
	//}
	for i, r := range term {
		partialTerm := string([]rune(term)[:i+1])
		log.Printf("  输入: '%s'", partialTerm)

		suggestURL := fmt.Sprintf("https://www.google.com/complete/search?q=%s&cp=%d&client=gws-wiz&xssi=t&gs_pcrt=undefined&hl=zh-CN&authuser=0&psi=%s&dpr=1",
			url.QueryEscape(partialTerm), len(string(r)), pd.PSI)
		searchC.Visit(suggestURL) // 使用searchC获取建议

		// 每次打字后也发送交互信标
		interactionURL := fmt.Sprintf("https://www.google.com/gen_204?atyp=i&ei=%s&ved=%s&bl=%s&s=webhp&zx=%d&opi=%s",
			pd.EI, pd.VED, pd.BL, time.Now().UnixMilli(), pd.OPI)
		gen_204C.Visit(interactionURL) // 使用beaconC发送信标

		time.Sleep(time.Duration(150+rand.Intn(200)) * time.Millisecond)
	}
}

// 修改后的 executeFirstSearch 函数
func executeFirstSearch(c *colly.Collector, pd *GooglePageData, term string, gsLp string) {
	// 1. 日志记录：这是一个好习惯，让我们在程序运行时能清楚地知道执行到了哪一步。
	log.Printf("\n--- 流程4: 发起对 '%s' 的第一次搜索 ---", term)

	// 2. 构建URL参数：我们不直接拼接字符串，而是使用 Go 标准库的 `url.Values`。
	//    这样做的好处是它会自动为我们处理URL编码，避免特殊字符（如空格、中文）导致URL格式错误。
	params := url.Values{}
	params.Add("q", term)           // 添加搜索词
	params.Add("source", "hp")      // 'hp' 通常表示请求来自 homepage
	params.Add("ei", pd.EI)         // 从档案袋中取出 Event ID
	params.Add("iflsig", pd.Iflsig) // 从档案袋中取出 iflsig 令牌
	if pd.VED != "" {
		params.Add("ved", pd.VED) // Visual Element Data，如果存在就添加
	}
	params.Add("uact", "5") // 一个表示用户行为的标志，通常是固定的
	params.Add("oq", term)  // Original Query，原始查询，通常与q相同
	if pd.Sclient != "" {
		params.Add("sclient", pd.Sclient) // Search Client，通常是 "gws-wiz"
	}
	if pd.OPI != "" {
		params.Add("opi", pd.OPI) // Opaque Parameter for Interactions，如果存在就添加
	}

	// 关键一步：将我们花费大力气生成的 gs_lp 添加到参数中
	if gsLp != "" {
		params.Add("gs_lp", gsLp)
	}

	// 3. 组装最终的URL：将基础URL和编码后的参数用 '?' 连接起来。
	firstSearchURL := "https://www.google.com/search?" + params.Encode()
	log.Println("  构建第一次搜索URL:", firstSearchURL)

	// 4. 【核心逻辑】发起请求，并为这个请求打上“标记”
	//    我们不再使用临时的OnResponse回调，因为那既不标准也无法工作。
	//    正确的做法是，为这个特定的请求创建一个“上下文(Context)”。
	ctx := colly.NewContext()

	//    在这个上下文中，我们放入一个键值对，就像给这个请求贴上一个标签。
	//    这个标签的内容是 "first_search_response"，告诉后续的回调：“嗨，我是第一次搜索的请求！”
	ctx.Put("request_stage", "first_search_response")

	// 5. 发起请求：
	//    我们必须使用 c.Request() 而不是 c.Visit()。
	//    因为只有 c.Request() 方法才允许我们把自定义的 Context 对象一起发出去。
	//    这个请求发出后，它的生命周期就暂时结束了。程序的控制权会继续往下走。
	//    当服务器返回响应时，searchC 上注册的 OnResponse 回调函数才会被触发。
	err := c.Request("GET", firstSearchURL, nil, ctx, nil)
	if err != nil {
		log.Printf("[ERROR] 发起第一次搜索请求失败: %v", err)
	}
}
