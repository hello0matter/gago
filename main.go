package main

import (
	"encoding/json"
	"fmt"
	"github.com/gocolly/colly"
	"log"
	"math/rand"
	"net/url"
	"os"
	"regexp"
	"time"
)

// SearchResult 结构体，用于存放最终结果
type SearchResult struct {
	Rank    int    `json:"rank"`
	URL     string `json:"url"`
	Title   string `json:"title"`
	Snippet string `json:"snippet"`
}

// GooglePageData 结构体，存放所有状态参数
type GooglePageData struct {
	EI           string
	PSI          string
	OPI          string
	BL           string
	VED          string
	JSController string
	Iflsig       string
	ClickCounter int
}

var gCheckRegex = regexp.MustCompile(`var\s*_g\s*=\s*\{`)

func main() {
	searchTerm := "colly golang"
	var finalResults []SearchResult
	var pageData GooglePageData
	rand.Seed(time.Now().UnixNano())

	initC := colly.NewCollector(
		colly.UserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"),
	)
	beaconC := initC.Clone()
	searchC := initC.Clone()

	/*
	 * ==================================================================
	 *                        1. 初始化流程 (initC)
	 * ==================================================================
	 */

	// 提取HTML属性中的参数 (不变)
	initC.OnHTML("input[name=ei]", func(e *colly.HTMLElement) {
		pageData.EI = e.Attr("value")
		pageData.PSI = e.Attr("value")
	})
	initC.OnHTML("input[name=iflsig]", func(e *colly.HTMLElement) { pageData.Iflsig = e.Attr("value") })
	initC.OnHTML("textarea[name=q]", func(e *colly.HTMLElement) { pageData.VED = e.Attr("data-ved") })
	initC.OnHTML("div[jscontroller][jsname=gLFyf]", func(e *colly.HTMLElement) { pageData.JSController = e.Attr("jscontroller") })

	// --- 关键修改部分 ---
	initC.OnHTML("script", func(e *colly.HTMLElement) {
		// --- 1. 新增功能: 自动访问外部JS文件 ---
		if jsSrc := e.Attr("src"); jsSrc != "" {
			jsURL := e.Request.AbsoluteURL(jsSrc)
			log.Printf("[initC] 发现并访问外部JS文件: %s", jsURL)
			beaconC.Visit(jsURL) // 使用 beaconC 访问，因为我们不关心响应内容
			return               // 处理完外部JS后，直接返回，不处理内部文本
		}

		// --- 2. 原有功能: 解析内部JS变量 ---
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

	// OnScraped, 搜索结果解析, 启动流程等其他部分完全不变...
	// (此处省略剩余代码，因为它们和您提供的版本完全一样)
	initC.OnScraped(func(r *colly.Response) {
		log.Println("[initC] 首页参数提取完成。")
		log.Printf("  > EI: %s, Iflsig: %s, VED: %s, OPI: %s, BL: %s, JSController: %s",
			pageData.EI, pageData.Iflsig, pageData.VED, pageData.OPI, pageData.BL, pageData.JSController)

		if pageData.EI == "" || pageData.Iflsig == "" {
			log.Fatal("关键参数EI或iflsig提取失败，流程终止。")
		}

		// 触发流程2：模拟点击输入框
		simulateClick(beaconC, &pageData)

		// 触发流程3：模拟逐字输入
		simulateTyping(searchC, beaconC, &pageData, searchTerm)

		// 触发流程4：执行最终搜索
		executeSearch(searchC, &pageData, searchTerm)
	})

	searchC.OnHTML("div.g", func(e *colly.HTMLElement) {
		if e.ChildText("h3") == "" {
			return
		}
		finalResults = append(finalResults, SearchResult{
			Rank:    len(finalResults) + 1,
			Title:   e.ChildText("h3"),
			URL:     e.ChildAttr("a", "href"),
			Snippet: e.ChildText("div[data-sncf]"),
		})
	})

	log.Println("--- 流程1: 访问主页并提取参数 ---")
	initC.Visit("https://www.google.com/")

	// 等待所有异步任务完成
	initC.Wait()
	beaconC.Wait()
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
func simulateClick(c *colly.Collector, pd *GooglePageData) {
	log.Println("\n--- 流程2: 模拟点击输入框 (发送全套信标) ---")
	if pd.VED == "" || pd.JSController == "" {
		log.Println("  [警告] 缺少VED或JSController，跳过点击信标发送。")
		return
	}
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
func simulateTyping(searchC, beaconC *colly.Collector, pd *GooglePageData, term string) {
	log.Printf("\n--- 流程3: 模拟输入关键词 '%s' ---", term)
	if pd.PSI == "" {
		log.Println("  [警告] 缺少PSI，跳过模拟输入步骤。")
		return
	}
	for i, r := range term {
		partialTerm := string([]rune(term)[:i+1])
		log.Printf("  输入: '%s'", partialTerm)

		suggestURL := fmt.Sprintf("https://www.google.com/complete/search?q=%s&cp=%d&client=gws-wiz&xssi=t&gs_pcrt=undefined&hl=zh-CN&authuser=0&psi=%s&dpr=1",
			url.QueryEscape(partialTerm), len(string(r)), pd.PSI)
		searchC.Visit(suggestURL) // 使用searchC获取建议

		// 每次打字后也发送交互信标
		interactionURL := fmt.Sprintf("https://www.google.com/gen_204?atyp=i&ei=%s&ved=%s&bl=%s&s=webhp&zx=%d&opi=%s",
			pd.EI, pd.VED, pd.BL, time.Now().UnixMilli(), pd.OPI)
		beaconC.Visit(interactionURL) // 使用beaconC发送信标

		time.Sleep(time.Duration(150+rand.Intn(200)) * time.Millisecond)
	}
}

// --- 流程4的辅助函数 ---
func executeSearch(c *colly.Collector, pd *GooglePageData, term string) {
	log.Printf("\n--- 流程4: 发起对 '%s' 的最终搜索 ---", term)
	finalURL := fmt.Sprintf("https://www.google.com/search?q=%s&ei=%s&iflsig=%s&opi=%s",
		url.QueryEscape(term), pd.EI, pd.Iflsig, pd.OPI)
	c.Visit(finalURL)
}
