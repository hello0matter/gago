package yagooglesearchpackage

import (
	"encoding/json"
	"fmt"
	"github.com/PuerkitoBio/goquery"
	"io/ioutil"
	"log"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const version = "1.10.0"

var (
	rootLogger  *log.Logger
	userAgents  []string
	resultLangs []string
	userAgent   = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36"
)

func init() {
	// Initialize logging
	logFile, err := os.OpenFile("yagooglesearch.go.log", os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666)
	if err != nil {
		log.Fatalf("Error opening log file: %v", err)
	}
	rootLogger = log.New(logFile, "", log.Ldate|log.Ltime|log.Lshortfile)

	// Load user agents
	installFolder := filepath.Dir(os.Args[0])
	userAgentsFile := filepath.Join(installFolder, "user_agents.txt")
	if _, err := os.Stat(userAgentsFile); err == nil {
		data, err := ioutil.ReadFile(userAgentsFile)
		if err != nil {
			rootLogger.Fatalf("Error reading user_agents.txt: %v", err)
		}
		userAgents = strings.Split(string(data), "\n")
	} else {
		userAgents = []string{userAgent}
	}

	// Load result languages
	resultLangsFile := filepath.Join(installFolder, "result_languages.txt")
	if _, err := os.Stat(resultLangsFile); err == nil {
		data, err := ioutil.ReadFile(resultLangsFile)
		if err != nil {
			rootLogger.Fatalf("Error reading result_languages.txt: %v", err)
		}
		lines := strings.Split(string(data), "\n")
		for _, line := range lines {
			if parts := strings.SplitN(line, "=", 2); len(parts) == 2 {
				resultLangs = append(resultLangs, parts[0])
			}
		}
	}
}

func getTbs(fromDate, toDate time.Time) string {
	return fmt.Sprintf("cdr:1,cd_min:%s,cd_max:%s", fromDate.Format("01/02/2006"), toDate.Format("01/02/2006"))
}

type SearchClient struct {
	query                           string
	tld                             string
	langHtmlUI                      string
	langResult                      string
	tbs                             string
	safe                            string
	start                           int
	num                             int
	country                         string
	extraParams                     map[string]string
	maxSearchResultURLsToReturn     int
	minimumDelayBetweenPagedResults int
	userAgent                       string
	manageHttp429s                  bool
	http429CoolOffTime              int
	http429CoolOffFactor            float64
	proxy                           string
	verifySSL                       bool
	verbosity                       int
	verboseOutput                   bool
	googleExemption                 string
	cookies                         map[string]string
	urlParameters                   []string
}

func NewSearchClient(
	query string,
	tld string,
	langHtmlUI string,
	langResult string,
	tbs string,
	safe string,
	start int,
	num int,
	country string,
	extraParams map[string]string,
	maxSearchResultURLsToReturn int,
	minimumDelayBetweenPagedResults int,
	userAgent string,
	manageHttp429s bool,
	http429CoolOffTime int,
	http429CoolOffFactor float64,
	proxy string,
	verifySSL bool,
	verbosity int,
	verboseOutput bool,
	googleExemption string,
) *SearchClient {
	sc := &SearchClient{
		query:                           query,
		tld:                             tld,
		langHtmlUI:                      langHtmlUI,
		langResult:                      langResult,
		tbs:                             tbs,
		safe:                            safe,
		start:                           start,
		num:                             num,
		country:                         country,
		extraParams:                     extraParams,
		maxSearchResultURLsToReturn:     maxSearchResultURLsToReturn,
		minimumDelayBetweenPagedResults: minimumDelayBetweenPagedResults,
		userAgent:                       userAgent,
		manageHttp429s:                  manageHttp429s,
		http429CoolOffTime:              http429CoolOffTime,
		http429CoolOffFactor:            http429CoolOffFactor,
		proxy:                           proxy,
		verifySSL:                       verifySSL,
		verbosity:                       verbosity,
		verboseOutput:                   verboseOutput,
		googleExemption:                 googleExemption,
		urlParameters:                   []string{"btnG", "cr", "hl", "num", "q", "safe", "start", "tbs", "lr"},
	}

	if sc.userAgent == "" {
		sc.userAgent = sc.assignRandomUserAgent()
	}

	if sc.langResult != "" && !contains(resultLangs, sc.langResult) {
		rootLogger.Printf("%s is not a valid language result. Setting lang_result to \"lang_en\".", sc.langResult)
		sc.langResult = "lang_en"
	}

	if sc.num > 100 {
		rootLogger.Println("The largest value allowed by Google for num is 100. Setting num to 100.")
		sc.num = 100
	}

	if sc.maxSearchResultURLsToReturn > 400 {
		rootLogger.Println("yagooglesearch is usually only able to retrieve a maximum of ~400 results.")
	}

	if sc.googleExemption != "" {
		sc.cookies = map[string]string{"GOOGLE_ABUSE_EXEMPTION": sc.googleExemption}
	}

	return sc
}

func (sc *SearchClient) assignRandomUserAgent() string {
	return userAgents[rand.Intn(len(userAgents))]
}

func (sc *SearchClient) filterSearchResultURLs(link string) string {
	if strings.HasPrefix(link, "/url?") || strings.HasPrefix(link, "http://www.google.com/url?") {
		parsedURL, err := url.Parse(link)
		if err != nil {
			return ""
		}
		queryParams := parsedURL.Query()
		if q, ok := queryParams["q"]; ok {
			link = q[0]
		} else if u, ok := queryParams["url"]; ok {
			link = u[0]
		}
	}

	parsedURL, err := url.Parse(link)
	if err != nil || parsedURL.Host == "" || strings.Contains(strings.ToLower(parsedURL.Host), "google") {
		return ""
	}

	return link
}

func (sc *SearchClient) http429Detected() {
	sc.http429CoolOffTime = int(float64(sc.http429CoolOffTime) * sc.http429CoolOffFactor)
	rootLogger.Printf("Increasing HTTP 429 cool off time to %d minutes", sc.http429CoolOffTime)
}

func (sc *SearchClient) getPage(url1 string) (string, error) {
	client := &http.Client{}
	if sc.proxy != "" {
		proxyURL, err := url.Parse(sc.proxy)
		if err != nil {
			return "", err
		}
		client.Transport = &http.Transport{Proxy: http.ProxyURL(proxyURL)}
	}

	req, err := http.NewRequest("GET", url1, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("User-Agent", sc.userAgent)
	if sc.cookies != nil {
		for key, value := range sc.cookies {
			req.AddCookie(&http.Cookie{Name: key, Value: value})
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	if resp.StatusCode == 429 {
		if !sc.manageHttp429s {
			return "HTTP_429_DETECTED", nil
		}
		rootLogger.Printf("Sleeping for %d minutes...", sc.http429CoolOffTime)
		time.Sleep(time.Duration(sc.http429CoolOffTime) * time.Minute)
		sc.http429Detected()
		return sc.getPage(url1)
	}

	return string(body), nil
}

func (sc *SearchClient) search() ([]map[string]string, error) {
	var results []map[string]string
	totalValidLinksFound := 0

	if sc.extraParams == nil {
		sc.extraParams = make(map[string]string)
	}

	for builtinParam := range sc.extraParams {
		if contains(sc.urlParameters, builtinParam) {
			return nil, fmt.Errorf("GET parameter \"%s\" is overlapping with the built-in GET parameter", builtinParam)
		}
	}

	_, err := sc.getPage(fmt.Sprintf("https://www.google.%s/", sc.tld))
	if err != nil {
		return nil, err
	}

	for totalValidLinksFound < sc.maxSearchResultURLsToReturn {
		rootLogger.Printf("Stats: start=%d, num=%d, total_valid_links_found=%d / max_search_result_urls_to_return=%d",
			sc.start, sc.num, totalValidLinksFound, sc.maxSearchResultURLsToReturn)

		var url string
		if sc.start > 0 {
			if sc.num == 10 {
				url = fmt.Sprintf("https://www.google.%s/search?hl=%s&lr=%s&q=%s&start=%d&tbs=%s&safe=%s&cr=%s&filter=0",
					sc.tld, sc.langHtmlUI, sc.langResult, sc.query, sc.start, sc.tbs, sc.safe, sc.country)
			} else {
				url = fmt.Sprintf("https://www.google.%s/search?hl=%s&lr=%s&q=%s&start=%d&num=%d&tbs=%s&safe=%s&cr=%s&filter=0",
					sc.tld, sc.langHtmlUI, sc.langResult, sc.query, sc.start, sc.num, sc.tbs, sc.safe, sc.country)
			}
		} else {
			if sc.num == 10 {
				url = fmt.Sprintf("https://www.google.%s/search?hl=%s&lr=%s&q=%s&tbs=%s&safe=%s&cr=%s&filter=0",
					sc.tld, sc.langHtmlUI, sc.langResult, sc.query, sc.tbs, sc.safe, sc.country)
			} else {
				url = fmt.Sprintf("https://www.google.%s/search?hl=%s&lr=%s&q=%s&num=%d&tbs=%s&safe=%s&cr=%s&filter=0",
					sc.tld, sc.langHtmlUI, sc.langResult, sc.query, sc.num, sc.tbs, sc.safe, sc.country)
			}
		}

		for key, value := range sc.extraParams {
			url += fmt.Sprintf("&%s=%s", key, value)
		}

		body, err := sc.getPage(url)
		if err != nil {
			return nil, err
		}

		if body == "HTTP_429_DETECTED" {
			results = append(results, map[string]string{"error": "HTTP_429_DETECTED"})
			return results, nil
		}

		doc, err := goquery.NewDocumentFromReader(strings.NewReader(body))
		if err != nil {
			return nil, err
		}

		validLinksFoundInThisSearch := 0
		doc.Find("a").Each(func(_ int, s *goquery.Selection) {
			link, exists := s.Attr("href")
			if !exists {
				return
			}

			link = sc.filterSearchResultURLs(link)
			if link == "" {
				return
			}

			if sc.verboseOutput {
				title := s.Text()
				description := s.Parent().Parent().Contents().Eq(1).Text()
				if description == "" {
					description = s.Parent().Parent().Contents().Eq(2).Text()
				}

				results = append(results, map[string]string{
					"rank":        fmt.Sprintf("%d", totalValidLinksFound+1),
					"title":       title,
					"description": description,
					"url":         link,
				})
			} else {
				results = append(results, map[string]string{"url": link})
			}

			totalValidLinksFound++
			validLinksFoundInThisSearch++
			if totalValidLinksFound >= sc.maxSearchResultURLsToReturn {
				return
			}
		})

		if validLinksFoundInThisSearch == 0 {
			rootLogger.Println("No valid search results found on this page. Moving on...")
			break
		}

		sc.start += sc.num
		time.Sleep(time.Duration(rand.Intn(12)+sc.minimumDelayBetweenPagedResults) * time.Second)
	}

	return results, nil
}

func contains(slice []string, item string) bool {
	for _, a := range slice {
		if a == item {
			return true
		}
	}
	return false
}

func main() {
	// Example usage
	sc := NewSearchClient(
		"example query",
		"com",
		"en",
		"lang_en",
		"",
		"off",
		0,
		10,
		"",
		nil,
		100,
		7,
		"",
		true,
		60,
		1.1,
		"",
		true,
		5,
		false,
		"",
	)

	results, err := sc.search()
	if err != nil {
		rootLogger.Fatalf("Error during search: %v", err)
	}

	jsonResults, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		rootLogger.Fatalf("Error marshaling results to JSON: %v", err)
	}

	fmt.Println(string(jsonResults))
}
