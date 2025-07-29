package yagooglesearch

import (
	"bufio"
	"crypto/tls"
	"fmt"
	"log"
	"math/rand"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
)

const Version = "1.10.0"

var (
	USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36"

	userAgentsList      []string
	resultLanguagesList []string

	// Logger setup
	logger *log.Logger
)

func init() {
	// Initialize logger
	logger = log.New(os.Stdout, "yagooglesearch ", log.LstdFlags)

	// Load user agents
	installFolder, _ := filepath.Abs(filepath.Dir(os.Args[0]))
	userAgentsFile := filepath.Join(installFolder, "user_agents.txt")

	if file, err := os.Open(userAgentsFile); err == nil {
		defer file.Close()
		scanner := bufio.NewScanner(file)
		for scanner.Scan() {
			userAgentsList = append(userAgentsList, strings.TrimSpace(scanner.Text()))
		}
	} else {
		userAgentsList = []string{USER_AGENT}
	}

	// Load result languages
	resultLanguagesFile := filepath.Join(installFolder, "result_languages.txt")

	if file, err := os.Open(resultLanguagesFile); err == nil {
		defer file.Close()
		scanner := bufio.NewScanner(file)
		for scanner.Scan() {
			parts := strings.Split(strings.TrimSpace(scanner.Text()), "=")
			if len(parts) > 0 {
				resultLanguagesList = append(resultLanguagesList, parts[0])
			}
		}
	} else {
		fmt.Printf("There was an issue loading the result languages file. Exception: %v\n", err)
		resultLanguagesList = []string{}
	}
}

// GetTbs formats the tbs parameter dates
func GetTbs(fromDate, toDate time.Time) string {
	fromDateStr := fromDate.Format("1/2/2006")
	toDateStr := toDate.Format("1/2/2006")
	return fmt.Sprintf("cdr:1,cd_min:%s,cd_max:%s", fromDateStr, toDateStr)
}

// SearchClient represents a Google search client
type SearchClient struct {
	Query                                    string
	Tld                                      string
	LangHtmlUI                               string
	LangResult                               string
	Tbs                                      string
	Safe                                     string
	Start                                    int
	Num                                      int
	Country                                  string
	ExtraParams                              map[string]string
	MaxSearchResultUrlsToReturn              int
	MinimumDelayBetweenPagedResultsInSeconds int
	UserAgent                                string
	YagooglesearchManagesHttp429s            bool
	Http429CoolOffTimeInMinutes              int
	Http429CoolOffFactor                     float64
	Proxy                                    string
	VerifySsl                                bool
	Verbosity                                int
	VerboseOutput                            bool
	GoogleExemption                          string

	// Internal fields
	Cookies          map[string]string
	UrlParameters    []string
	ProxyDict        map[string]string
	SearchResultList []interface{}
}

// NewSearchClient creates a new SearchClient
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
	maxSearchResultUrlsToReturn int,
	minimumDelayBetweenPagedResultsInSeconds int,
	userAgent string,
	yagooglesearchManagesHttp429s bool,
	http429CoolOffTimeInMinutes int,
	http429CoolOffFactor float64,
	proxy string,
	verifySsl bool,
	verbosity int,
	verboseOutput bool,
	googleExemption string,
) *SearchClient {
	client := &SearchClient{
		Query:                                    url.QueryEscape(query),
		Tld:                                      tld,
		LangHtmlUI:                               langHtmlUI,
		LangResult:                               formatLangResult(langResult),
		Tbs:                                      tbs,
		Safe:                                     safe,
		Start:                                    start,
		Num:                                      num,
		Country:                                  country,
		ExtraParams:                              extraParams,
		MaxSearchResultUrlsToReturn:              maxSearchResultUrlsToReturn,
		MinimumDelayBetweenPagedResultsInSeconds: minimumDelayBetweenPagedResultsInSeconds,
		UserAgent:                                userAgent,
		YagooglesearchManagesHttp429s:            yagooglesearchManagesHttp429s,
		Http429CoolOffTimeInMinutes:              http429CoolOffTimeInMinutes,
		Http429CoolOffFactor:                     http429CoolOffFactor,
		Proxy:                                    proxy,
		VerifySsl:                                verifySsl,
		Verbosity:                                verbosity,
		VerboseOutput:                            verboseOutput,
		GoogleExemption:                          googleExemption,

		// Initialize internal fields
		UrlParameters:    []string{"btnG", "cr", "hl", "num", "q", "safe", "start", "tbs", "lr"},
		SearchResultList: []interface{}{},
	}

	// Argument checks
	if !containsString(resultLanguagesList, client.LangResult) {
		logger.Printf("%s is not a valid language result. Setting lang_result to \"lang_en\".", client.LangResult)
		client.LangResult = "lang_en"
	}

	if client.Num > 100 {
		logger.Println("The largest value allowed by Google for num is 100. Setting num to 100.")
		client.Num = 100
	}

	if client.MaxSearchResultUrlsToReturn > 400 {
		logger.Println("yagooglesearch is usually only able to retrieve a maximum of ~400 results. See README for more details.")
	}

	// Populate cookies
	if client.GoogleExemption != "" {
		client.Cookies = map[string]string{
			"GOOGLE_ABUSE_EXEMPTION": client.GoogleExemption,
		}
	} else {
		client.Cookies = nil
	}

	// Set user agent
	if client.UserAgent == "" {
		client.UserAgent = client.assignRandomUserAgent()
	}

	// Update URLs
	client.updateUrls()

	// Initialize proxy dict
	client.ProxyDict = make(map[string]string)
	if client.Proxy != "" {
		client.ProxyDict["http"] = client.Proxy
		client.ProxyDict["https"] = client.Proxy
	}

	return client
}

// formatLangResult formats the language result parameter
func formatLangResult(langResult string) string {
	if !strings.Contains(langResult, "-") {
		return strings.ToLower(langResult)
	}
	parts := strings.Split(langResult, "-")
	if len(parts) >= 2 {
		return fmt.Sprintf("%s-%s", strings.ToLower(parts[0]), strings.ToUpper(parts[1]))
	}
	return strings.ToLower(langResult)
}

// containsString checks if a string is in a slice
func containsString(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

// updateUrls updates search URLs being used
func (sc *SearchClient) updateUrls() {
	// URL templates to make Google searches
	sc.urlHome = fmt.Sprintf("https://www.google.%s/", sc.Tld)

	// First search requesting the default 10 search results
	sc.urlSearch = fmt.Sprintf(
		"https://www.google.%s/search?hl=%s&lr=%s&q=%s&btnG=Google+Search&tbs=%s&safe=%s&cr=%s&filter=0",
		sc.Tld, sc.LangHtmlUI, sc.LangResult, sc.Query, sc.Tbs, sc.Safe, sc.Country)

	// Subsequent searches starting at &start= and retrieving 10 search results at a time
	sc.urlNextPage = fmt.Sprintf(
		"https://www.google.%s/search?hl=%s&lr=%s&q=%s&start=%d&tbs=%s&safe=%s&cr=%s&filter=0",
		sc.Tld, sc.LangHtmlUI, sc.LangResult, sc.Query, sc.Start, sc.Tbs, sc.Safe, sc.Country)

	// First search requesting more than the default 10 search results
	sc.urlSearchNum = fmt.Sprintf(
		"https://www.google.%s/search?hl=%s&lr=%s&q=%s&num=%d&btnG=Google+Search&tbs=%s&safe=%s&cr=%s&filter=0",
		sc.Tld, sc.LangHtmlUI, sc.LangResult, sc.Query, sc.Num, sc.Tbs, sc.Safe, sc.Country)

	// Subsequent searches starting at &start= and retrieving &num= search results at a time
	sc.urlNextPageNum = fmt.Sprintf(
		"https://www.google.%s/search?hl=%s&lr=%s&q=%s&start=%d&num=%d&tbs=%s&safe=%s&cr=%s&filter=0",
		sc.Tld, sc.LangHtmlUI, sc.LangResult, sc.Query, sc.Start, sc.Num, sc.Tbs, sc.Safe, sc.Country)
}

// assignRandomUserAgent assigns a random user agent string
func (sc *SearchClient) assignRandomUserAgent() string {
	randomUserAgent := userAgentsList[rand.Intn(len(userAgentsList))]
	sc.UserAgent = randomUserAgent
	return randomUserAgent
}

// filterSearchResultUrls filters links found in the Google result pages HTML code
func (sc *SearchClient) filterSearchResultUrls(link string) string {
	logger.Printf("pre filter_search_result_urls() link: %s", link)

	defer func() {
		logger.Printf("post filter_search_result_urls() link: %s", link)
	}()

	// Extract URL from parameter
	if strings.HasPrefix(link, "/url?") || strings.HasPrefix(link, "http://www.google.com/url?") {
		parsedUrl, err := url.Parse(link)
		if err != nil {
			link = ""
			return link
		}

		params := parsedUrl.Query()
		if q, ok := params["q"]; ok && len(q) > 0 {
			link = q[0]
		} else if urlParam, ok := params["url"]; ok && len(urlParam) > 0 {
			link = urlParam[0]
		}
	}

	// Parse the URL
	parsedUrl, err := url.Parse(link)
	if err != nil || parsedUrl.Host == "" {
		logger.Printf("Excluding URL because it does not contain a netloc value: %s", link)
		link = ""
		return link
	}

	// Exclude Google domains
	if strings.Contains(strings.ToLower(parsedUrl.Host), "google") {
		logger.Printf("Excluding URL because it contains \"google\": %s", link)
		link = ""
		return link
	}

	return link
}

// http429Detected increases the HTTP 429 cool off period
func (sc *SearchClient) http429Detected() {
	newHttp429CoolOffTimeInMinutes := int(float64(sc.Http429CoolOffTimeInMinutes) * sc.Http429CoolOffFactor)
	logger.Printf(
		"Increasing HTTP 429 cool off time by a factor of %f, from %d minutes to %d minutes",
		sc.Http429CoolOffFactor, sc.Http429CoolOffTimeInMinutes, newHttp429CoolOffTimeInMinutes)
	sc.Http429CoolOffTimeInMinutes = newHttp429CoolOffTimeInMinutes
}

// getPage requests the given URL and returns the response page
func (sc *SearchClient) getPage(urlStr string) (string, error) {
	headers := map[string]string{
		"User-Agent": sc.UserAgent,
	}

	logger.Printf("Requesting URL: %s", urlStr)

	// Create HTTP client with optional proxy and SSL settings
	client := &http.Client{
		Timeout: 15 * time.Second,
	}

	if !sc.VerifySsl {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	// TODO: Add proxy support

	req, err := http.NewRequest("GET", urlStr, nil)
	if err != nil {
		return "", err
	}

	// Set headers
	for key, value := range headers {
		req.Header.Set(key, value)
	}

	// TODO: Add cookie support

	response, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer response.Body.Close()

	// Extract the HTTP response code
	httpResponseCode := response.StatusCode
	logger.Printf("    status_code: %d", httpResponseCode)
	logger.Printf("    headers: %v", headers)
	// TODO: Log cookies, proxy, verify_ssl

	// Handle different response codes
	switch httpResponseCode {
	case 200:
		// TODO: Read response body
		return "", nil
	case 429:
		logger.Println("Google is blocking your IP for making too many requests in a specific time period.")

		// Calling script does not want yagooglesearch to handle HTTP 429 cool off and retry
		if !sc.YagooglesearchManagesHttp429s {
			logger.Println("Since yagooglesearch_manages_http_429s=False, yagooglesearch is done.")
			return "HTTP_429_DETECTED", nil
		}

		logger.Printf("Sleeping for %d minutes...", sc.Http429CoolOffTimeInMinutes)
		time.Sleep(time.Duration(sc.Http429CoolOffTimeInMinutes) * time.Minute)
		sc.http429Detected()

		// Try making the request again
		return sc.getPage(urlStr)
	default:
		logger.Printf("HTML response code: %d", httpResponseCode)
		return "", nil
	}
}

// Search starts the Google search
func (sc *SearchClient) Search() ([]interface{}, error) {
	// Consolidate search results
	sc.SearchResultList = []interface{}{}

	// Count the number of valid, non-duplicate links found
	totalValidLinksFound := 0

	// If no extraParams is given, create an empty dictionary
	if sc.ExtraParams == nil {
		sc.ExtraParams = make(map[string]string)
	}

	// Check extra_params for overlapping parameters
	for _, builtinParam := range sc.UrlParameters {
		if _, exists := sc.ExtraParams[builtinParam]; exists {
			return nil, fmt.Errorf("GET parameter \"%s\" is overlapping with the built-in GET parameter", builtinParam)
		}
	}

	// Simulates browsing to the https://www.google.com home page and retrieving the initial cookie
	_, err := sc.getPage(sc.urlHome)
	if err != nil {
		return nil, err
	}

	// Loop until we reach the maximum result results found or there are no more search results found to reach max_search_result_urls_to_return
	for totalValidLinksFound <= sc.MaxSearchResultUrlsToReturn {
		logger.Printf(
			"Stats: start=%d, num=%d, total_valid_links_found=%d / max_search_result_urls_to_return=%d",
			sc.Start, sc.Num, totalValidLinksFound, sc.MaxSearchResultUrlsToReturn)

		// Prepare the URL for the search request
		var urlStr string
		if sc.Start > 0 {
			if sc.Num == 10 {
				urlStr = sc.urlNextPage
			} else {
				urlStr = sc.urlNextPageNum
			}
		} else {
			if sc.Num == 10 {
				urlStr = sc.urlSearch
			} else {
				urlStr = sc.urlSearchNum
			}
		}

		// Append extra GET parameters to the URL
		params := url.Values{}
		for key, value := range sc.ExtraParams {
			params.Add(key, value)
		}
		if len(params) > 0 {
			urlStr += "&" + params.Encode()
		}

		// Request Google search results
		html, err := sc.getPage(urlStr)
		if err != nil {
			return nil, err
		}

		// HTTP 429 message returned from get_page() function
		if html == "HTTP_429_DETECTED" {
			sc.SearchResultList = append(sc.SearchResultList, "HTTP_429_DETECTED")
			return sc.SearchResultList, nil
		}

		// Create the goquery document
		doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
		if err != nil {
			return nil, err
		}

		// Find all HTML <a> elements
		var anchors *goquery.Selection
		if search := doc.Find("#search"); search.Length() > 0 {
			anchors = search.Find("a")
		} else {
			// Remove links from the top bar
			if gbar := doc.Find("#gbar"); gbar.Length() > 0 {
				gbar.Remove()
			}
			anchors = doc.Find("a")
		}

		// Tracks number of valid URLs found on a search page
		validLinksFoundInThisSearch := 0

		// Process every anchored URL
		anchors.Each(func(i int, a *goquery.Selection) {
			// Get the URL from the anchor tag
			link, exists := a.Attr("href")
			if !exists {
				logger.Printf("No href for link: %s", link)
				return
			}

			// Filter invalid links and links pointing to Google itself
			link = sc.filterSearchResultUrls(link)
			if link == "" {
				return
			}

			var title, description string
			if sc.VerboseOutput {
				// Extract the URL title
				title = a.Text()

				// Extract the URL description
				// TODO: Implement description extraction
				description = ""
			}

			// Check if URL has already been found
			alreadyFound := false
			for _, result := range sc.SearchResultList {
				if result == link {
					alreadyFound = true
					break
				}
			}

			if !alreadyFound {
				// Increase the counters
				validLinksFoundInThisSearch++
				totalValidLinksFound++

				logger.Printf("Found unique URL #%d: %s", totalValidLinksFound, link)

				if sc.VerboseOutput {
					result := map[string]interface{}{
						"rank":        totalValidLinksFound,           // Approximate rank according to yagooglesearch
						"title":       strings.TrimSpace(title),       // Remove leading and trailing spaces
						"description": strings.TrimSpace(description), // Remove leading and trailing spaces
						"url":         link,
					}
					sc.SearchResultList = append(sc.SearchResultList, result)
				} else {
					sc.SearchResultList = append(sc.SearchResultList, link)
				}
			} else {
				logger.Printf("Duplicate URL found: %s", link)
			}

			// If we reached the limit of requested URLs, return with the results
			if sc.MaxSearchResultUrlsToReturn <= len(sc.SearchResultList) {
				return
			}
		})

		// Determining if a "Next" URL page of results is not straightforward. If no valid links are found, the search results have been exhausted.
		if validLinksFoundInThisSearch == 0 {
			logger.Println("No valid search results found on this page. Moving on...")
			return sc.SearchResultList, nil
		}

		// Bump the starting page URL parameter for the next request
		sc.Start += sc.Num

		// Refresh the URLs
		sc.updateUrls()

		// Randomize sleep time between paged requests to make it look more human
		randomSleepTime := sc.MinimumDelayBetweenPagedResultsInSeconds + rand.Intn(11)
		logger.Printf("Sleeping %d seconds until retrieving the next page of results...", randomSleepTime)
		time.Sleep(time.Duration(randomSleepTime) * time.Second)
	}

	return sc.SearchResultList, nil
}
