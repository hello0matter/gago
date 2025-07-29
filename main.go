package main

import (
	"fmt"
	"github.com/dop251/goja"
	"github.com/gocolly/colly"
	"log"
	"math/rand"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"
)

type GooglePageData struct {
	BeaconURLTemplate string
	PSI               string
	EI                string // 用于存储Goja生成的ei
}

func decodeJSStringURL(s string) string {
	s = strings.ReplaceAll(s, `\x3d`, `=`)
	s = strings.ReplaceAll(s, `\x26`, `&`)
	return s
}

// generateEI 使用Goja执行JS来生成ei参数
func generateEI(jsCode string) (string, error) {
	log.Println("--- [Goja] 开始执行JS以生成 'ei' ---")
	vm := goja.New()

	// --- 1. 构建模拟的浏览器环境 (保持不变) ---
	log.Println("[Goja] 正在构建模拟浏览器环境...")
	// ... (代码与之前完全相同, 为了简洁省略)
	window := vm.GlobalObject()
	vm.Set("window", window)
	vm.Set("navigator", map[string]interface{}{
		"userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
	})
	vm.Set("location", map[string]interface{}{"href": "https://www.google.com/"})
	vm.Set("document", map[string]interface{}{
		"addEventListener": func(call goja.FunctionCall) goja.Value {
			return goja.Undefined()
		},
	})
	errorConstructor := vm.Get("Error").ToObject(vm)
	errorConstructor.Set("captureStackTrace", func() {})
	vm.Set("TextEncoder", func() {})
	vm.Set("TextDecoder", func() {})
	vm.Set("setTimeout", func(call goja.FunctionCall) goja.Value {
		return goja.Undefined()
	})
	vm.Set("performance", map[string]interface{}{
		"now": func() float64 {
			return float64(time.Now().UnixNano()) / 1e6
		},
	})
	vm.Set("crypto", map[string]interface{}{
		"getRandomValues": func(call goja.FunctionCall) goja.Value {
			arg := call.Argument(0)
			if obj, ok := arg.(*goja.Object); ok {
				lengthVal := obj.Get("length")
				if length, ok := lengthVal.Export().(int64); ok {
					randomBytes := make([]byte, length)
					_, _ = rand.Read(randomBytes)
					for i := 0; i < int(length); i++ {
						obj.Set(fmt.Sprint(i), randomBytes[i])
					}
				}
			}
			return arg
		},
	})
	log.Println("[Goja] 模拟环境构建完毕。")

	// --- 2. 执行核心的 Google JS 代码 ---
	log.Println("[Goja] 正在执行核心JS代码...")

	_, err := vm.RunString("var _hd = {};")
	if err != nil {
		return "", fmt.Errorf("[Goja] 初始化_hd失败: %w", err)
	}

	// 【核心修复】在这里为我们模拟的 google 对象添加 dl 属性
	_, err = vm.RunString(`
		var google = {
			c: {},
			tick: function() { return; },
			dl: function() { return; } // 添加这个无害的 dl 函数，以通过 JS 的存在性检查
		};
	`)
	if err != nil {
		return "", fmt.Errorf("[Goja] 初始化google对象失败: %w", err)
	}
	log.Println("[Goja] 'google = {..., dl: function(){}}' 已成功注入。")

	// 之前的 "throw Error('va')" 补丁仍然需要，保持不变
	log.Println("[Goja] 正在修补(Patch)核心JS代码，移除致命错误...")
	originalCode := `throw Error("va")`
	patchedCode := `return {} /* Patched by Goja */`
	patchedJsCode := strings.Replace(jsCode, originalCode, patchedCode, -1)
	if patchedJsCode == jsCode {
		return "", fmt.Errorf("[Goja] 注入失败：无法在JS代码中找到错误代码 'throw Error(\"va\")'")
	}
	log.Println("[Goja] 致命错误已成功移除。")
	patchedJsCode = `

	`
	// 执行被我们修改过的JS文件
	_, err = vm.RunScript("google.js", patchedJsCode)
	if err != nil {
		if gojaErr, ok := err.(*goja.Exception); ok {
			log.Printf("[Goja] JS异常: %s", gojaErr.String())
		}
		return "", fmt.Errorf("[Goja] 执行JS失败: %w", err)
	}
	log.Println("[Goja] JS代码执行完毕。")

	// --- 3. 提取最终结果 (ei) (保持不变) ---
	log.Println("[Goja] 正在从JS环境中提取 'ei'...")
	// ... (提取逻辑与之前完全相同, 省略)
	var googleObj *goja.Object
	googleObjValue := vm.Get("google")
	if googleObjValue != nil && !goja.IsUndefined(googleObjValue) && !goja.IsNull(googleObjValue) {
		googleObj = googleObjValue.ToObject(vm)
	}
	if googleObj == nil {
		hdObjValue := vm.Get("_hd")
		if hdObjValue != nil && !goja.IsUndefined(hdObjValue) && !goja.IsNull(hdObjValue) {
			hdObj := hdObjValue.ToObject(vm)
			googleFromHd := hdObj.Get("google")
			if googleFromHd != nil && !goja.IsUndefined(googleFromHd) && !goja.IsNull(googleFromHd) {
				googleObj = googleFromHd.ToObject(vm)
			}
		}
	}
	if googleObj == nil {
		return "", fmt.Errorf("[Goja] 无法在JS环境中找到 'google' 或 '_hd.google' 对象")
	}

	eiValue := googleObj.Get("kEI")
	if goja.IsUndefined(eiValue) || goja.IsNull(eiValue) {
		csiValue := googleObj.Get("csi")
		if csiValue != nil && !goja.IsUndefined(csiValue) {
			csiObj := csiValue.ToObject(vm)
			if csiObj != nil {
				eiValue = csiObj.Get("ei")
			}
		}
		if goja.IsUndefined(eiValue) || goja.IsNull(eiValue) {
			return "", fmt.Errorf("[Goja] 无法从 'google' 对象中找到 'kEI' 或 'csi.ei' 属性")
		}
	}

	ei := eiValue.String()
	log.Printf("--- [Goja] 成功生成 'ei': %s ---", ei)
	return ei, nil
}
func main() {
	c := colly.NewCollector(
		colly.Async(true),
		colly.UserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"),
	)
	c.Limit(&colly.LimitRule{DomainGlob: "*.google.com", Parallelism: 6, RandomDelay: 1 * time.Second})

	headers := map[string]string{
		"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
	}

	pageData := &GooglePageData{}
	rand.Seed(time.Now().UnixNano())

	var mainJSCode string

	c.OnRequest(func(r *colly.Request) {
		for key, value := range headers {
			r.Headers.Set(key, value)
		}
		// ... 其他头部设置 ...
		log.Printf("=> 准备发起请求: %s...", r.URL.String())
	})

	c.OnHTML("script[src]", func(e *colly.HTMLElement) {
		scriptSrc := e.Attr("src")
		if strings.HasPrefix(scriptSrc, "/") {
			e.Request.Visit(scriptSrc)
		}
	})

	c.OnHTML("link[rel='stylesheet']", func(e *colly.HTMLElement) {
		styleHref := e.Attr("href")
		if strings.HasPrefix(styleHref, "/") {
			e.Request.Visit(styleHref)
		}
	})

	c.OnResponse(func(r *colly.Response) {
		log.Printf("<= 收到响应: %d %s", r.StatusCode, r.Request.URL.String())

		if strings.Contains(r.Request.URL.String(), "/js/") && strings.Contains(string(r.Body), "this._hd") {
			log.Println("[提取成功] 捕获到核心JS文件内容。")
			mainJSCode = string(r.Body)
		}

		if r.Request.URL.Path == "/" {
			htmlBody := string(r.Body)

			reURLTemplate := regexp.MustCompile(`url:\s*'(.*?)'`)
			if m := reURLTemplate.FindStringSubmatch(htmlBody); len(m) > 1 {
				pageData.BeaconURLTemplate = decodeJSStringURL(m[1])
				log.Println("[提取成功] Beacon URL 模板")
			}

			rePSI := regexp.MustCompile(`psi:'([^']*)'`)
			if m := rePSI.FindStringSubmatch(htmlBody); len(m) > 1 {
				pageData.PSI = m[1]
				log.Printf("[提取成功] Page Session ID (PSI): %s", pageData.PSI)
			}
		}
	})

	c.OnHTML("div#search div.g", func(e *colly.HTMLElement) {
		// ...
	})

	c.OnError(func(r *colly.Response, err error) {
		log.Printf("<= 请求错误: URL: %s, 状态码: %d, 错误: %v", r.Request.URL, r.StatusCode, err)
	})

	// ==================================================================
	// 执行流程
	// ==================================================================

	log.Println("--- 第1步: 访问主页并自动加载其所有JS/CSS资源 ---")
	c.Visit("https://www.google.com/")
	c.Wait()

	if mainJSCode == "" {
		log.Println("[警告] 未能从网络捕获核心JS，尝试从本地'google.js'文件加载...")
		jsBytes, err := os.ReadFile("google.js")
		if err != nil {
			log.Fatalf("从网络和本地加载核心JS均失败: %v", err)
		}
		mainJSCode = string(jsBytes)
	}

	ei, err := generateEI(mainJSCode)
	if err != nil {
		log.Fatalf("Goja生成ei失败: %v", err)
	}
	pageData.EI = ei

	if pageData.BeaconURLTemplate != "" {
		log.Println("--- 第2步: 发送信标 ---")
		beaconURL := "https://www.google.com" + pageData.BeaconURLTemplate + "&ei=" + pageData.EI
		c.Visit(beaconURL)
		c.Wait()
	} else {
		log.Println("[警告] 未找到信标URL，跳过此步骤。")
	}

	if pageData.PSI == "" {
		log.Println("[警告] 未提取到PSI, 模拟输入建议功能可能受影响。")
	}

	searchTerm := "golang web framework"
	log.Printf("\n--- 第3步: 模拟输入关键词 '%s' ---", searchTerm)

	if pageData.PSI != "" {
		for i := 1; i <= len(searchTerm); i++ {
			partialTerm := searchTerm[:i]
			if partialTerm[len(partialTerm)-1] == ' ' {
				continue
			}
			suggestURL := fmt.Sprintf(
				"https://www.google.com/complete/search?q=%s&client=gws-wiz&xssi=t&hl=zh-CN&psi=%s",
				url.QueryEscape(partialTerm),
				pageData.PSI,
			)
			c.Visit(suggestURL)

			delay := time.Duration(100+rand.Intn(150)) * time.Millisecond
			time.Sleep(delay)
		}
		c.Wait()
	} else {
		log.Println("[跳过] 因缺少PSI，跳过模拟输入建议步骤。")
	}

	log.Printf("\n--- 第4步: 发起对 '%s' 的最终搜索 ---", searchTerm)
	finalSearchURL := fmt.Sprintf("https://www.google.com/search?q=%s&ei=%s", url.QueryEscape(searchTerm), pageData.EI)
	c.Visit(finalSearchURL)
	c.Wait()

	log.Println("\n✅✅✅ 完整搜索流程模拟完毕。✅✅✅")
}
