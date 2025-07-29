package gosearch

import (
	"bufio"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"golang.org/x/net/publicsuffix"
)

var (
	userAgents []string
)

// init 函数在包被首次使用时自动执行，用于加载外部文件数据。
func init() {
	var err error
	// 路径是相对于项目根目录的。
	userAgents, err = loadLinesFromFile("gosearch/user_agents.txt")
	if err != nil {
		log.Fatalf("无法加载 user_agents.txt: %v。请确保文件存在且路径正确。", err)
	}
	if len(userAgents) == 0 {
		log.Println("[警告] user_agents.txt 为空或未找到，将使用默认UA")
		userAgents = []string{"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36"}
	}
}

// loadLinesFromFile 读取文件，将每一行作为一个字符串存入切片。
func loadLinesFromFile(filePath string) ([]string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var lines []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line != "" { // 忽略空行和注释
			lines = append(lines, line)
		}
	}
	return lines, scanner.Err()
}

// SearchClient 封装了执行Google搜索所需的所有状态和方法
type SearchClient struct {
	Query      string
	TLD        string
	LangResult string
	Num        int
	Proxy      string
	client     *http.Client
	userAgent  string
}

// SearchResult 代表一条搜索结果
type SearchResult struct {
	Rank  int
	URL   string
	Title string
}

// NewSearchClient 创建一个新的搜索客户端实例
func NewSearchClient(query, tld, langResult, proxy string) (*SearchClient, error) {
	jar, err := cookiejar.New(&cookiejar.Options{PublicSuffixList: publicsuffix.List})
	if err != nil {
		return nil, err
	}

	httpClient := &http.Client{
		Jar:     jar,
		Timeout: 20 * time.Second,
	}

	if proxy != "" {
		proxyURL, err := url.Parse(proxy)
		if err != nil {
			return nil, fmt.Errorf("无效的代理URL: %w", err)
		}
		httpClient.Transport = &http.Transport{Proxy: http.ProxyURL(proxyURL)}
	}

	rand.Seed(time.Now().UnixNano())
	return &SearchClient{
		Query:      query,
		TLD:        tld,
		LangResult: langResult,
		Num:        100,
		Proxy:      proxy,
		client:     httpClient,
		userAgent:  userAgents[rand.Intn(len(userAgents))],
	}, nil
}

// getPage 是一个内部帮助函数，用于获取和解析页面
func (sc *SearchClient) getPage(requestURL string) (*goquery.Document, error) {
	req, err := http.NewRequest("GET", requestURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", sc.userAgent)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.5")
	req.Header.Set("Referer", fmt.Sprintf("https://www.google.%s/", sc.TLD))
	req.Header.Set("Connection", "keep-alive")

	resp, err := sc.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("非200状态码: %s", resp.Status)
	}

	return goquery.NewDocumentFromReader(resp.Body)
}

// filterURL 从Google的跳转链接中提取真实URL
func (sc *SearchClient) filterURL(href string) string {
	if strings.HasPrefix(href, "/url?q=") {
		parsedURL, err := url.Parse(href)
		if err == nil {
			realURL := parsedURL.Query().Get("q")
			if realURL != "" && !strings.Contains(realURL, "google.com") {
				return realURL
			}
		}
	}
	return ""
}

// Search 是暴露给外部调用的主方法，执行搜索流程
func (sc *SearchClient) Search() ([]SearchResult, error) {
	log.Printf("[搜索] 使用UA: %s\n", sc.userAgent)

	// 1. 访问主页获取初始Cookie
	log.Println("[搜索] 正在访问 Google 主页以获取 Cookie...")
	_, err := sc.getPage(fmt.Sprintf("https://www.google.%s/", sc.TLD))
	if err != nil {
		return nil, fmt.Errorf("访问主页失败: %w", err)
	}
	time.Sleep(time.Duration(rand.Intn(1500)+500) * time.Millisecond)

	// 2. 构造并请求搜索URL
	params := url.Values{}
	params.Set("q", sc.Query)
	params.Set("hl", "en")
	params.Set("lr", sc.LangResult)
	params.Set("num", strconv.Itoa(sc.Num))
	params.Set("filter", "0")
	searchURL := fmt.Sprintf("https://www.google.%s/search?%s", sc.TLD, params.Encode())

	log.Printf("[搜索] 正在请求搜索URL: %s\n", searchURL)
	doc, err := sc.getPage(searchURL)
	if err != nil {
		return nil, fmt.Errorf("请求搜索页失败: %w", err)
	}

	// 3. 解析和提取结果
	var results []SearchResult
	rank := 1
	doc.Find("#search a, .g a, .yuRUbf a").Each(func(i int, s *goquery.Selection) {
		href, exists := s.Attr("href")
		if !exists {
			return
		}

		realURL := sc.filterURL(href)
		if realURL != "" {
			isDuplicate := false
			for _, r := range results {
				if r.URL == realURL {
					isDuplicate = true
					break
				}
			}

			if !isDuplicate {
				results = append(results, SearchResult{
					Rank:  rank,
					URL:   realURL,
					Title: s.Find("h3").First().Text(),
				})
				rank++
			}
		}
	})

	return results, nil
}
