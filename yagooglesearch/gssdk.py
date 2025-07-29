import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
import re
import time
import random
import urllib.parse
from bs4 import BeautifulSoup
import threading
import queue
from urllib.parse import urlparse, urljoin
import logging
from ttkthemes import ThemedTk

try:
    from yagooglesearch import SearchClient, tlds
except ImportError:
    tlds = ["com", "com.hk", "co.uk"]
    pass

# --- 内置数据 ---
USER_PROFILES = [
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "headers": {'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"'}},
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "headers": {'sec-ch-ua': '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
                    'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"macOS"'}}
]
REFERRERS = ["https://www.google.com/", "https://www.bing.com/", "https://t.co/", "https://www.facebook.com/", None]


class CustomSearchClient(SearchClient):
    def update_urls(self):
        self.url_home = f"https://www.google.{self.tld}/"
        base_query_params = (
            f"hl={self.lang_html_ui}&q={self.query}&tbs={self.tbs}&safe={self.safe}&cr={self.country}&filter=0")
        self.url_search = f"https://www.google.{self.tld}/search?{base_query_params}"
        self.url_search_num = f"https://www.google.{self.tld}/search?num={self.num}&{base_query_params}"
        self.url_next_page = f"https://www.google.{self.tld}/search?start={self.start}&{base_query_params}"
        self.url_next_page_num = f"https://www.google.{self.tld}/search?start={self.start}&num={self.num}&{base_query_params}"


class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(logging.Formatter('%(message)s'))

    def emit(self, record):
        self.log_queue.put(self.format(record))


class App(ThemedTk):
    def __init__(self):
        super().__init__(theme="arc")
        self.title("网站分析与GA模拟平台 V5.5 (URL拦截版)")
        self.geometry("1100x800")
        self.active_thread = None
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        self._create_widgets()
        self.after(100, self._process_log_queue_and_intercept)
        try:
            from yagooglesearch import SearchClient as Search
        except ImportError:
            messagebox.showerror("依赖库缺失", "未找到 yagooglesearch 库。\n请在终端运行: pip install yagooglesearch");
            self.destroy()

    def _create_widgets(self):
        # ... GUI布局代码和之前完全一样 ...
        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        control_frame = ttk.Frame(main_pane, width=380);
        main_pane.add(control_frame, weight=1)
        result_pane = ttk.PanedWindow(main_pane, orient=tk.VERTICAL);
        main_pane.add(result_pane, weight=3)
        tree_frame = ttk.LabelFrame(result_pane, text="网站结构 & GA标记", padding=10);
        result_pane.add(tree_frame, weight=2)
        log_frame = ttk.LabelFrame(result_pane, text="实时日志 (可编辑)", padding=10);
        result_pane.add(log_frame, weight=1)
        search_frame = ttk.LabelFrame(control_frame, text="模块 1: 谷歌搜索", padding=10);
        search_frame.pack(fill=tk.X, pady=5)
        ttk.Label(search_frame, text="关键词:").pack(anchor='w');
        self.keyword_entry = ttk.Entry(search_frame);
        self.keyword_entry.pack(fill=tk.X);
        self.keyword_entry.insert(0, "ad斗篷")
        ttk.Label(search_frame, text="目标域名:").pack(anchor='w');
        self.domain_entry = ttk.Entry(search_frame);
        self.domain_entry.pack(fill=tk.X);
        self.domain_entry.insert(0, "adcloaking.com")
        ttk.Label(search_frame, text="搜索地区 (TLD):").pack(anchor='w');
        self.tld_var = tk.StringVar(value='com.hk');
        self.tld_menu = ttk.Combobox(search_frame, textvariable=self.tld_var, values=tlds, state="readonly");
        self.tld_menu.pack(fill=tk.X)
        self.search_btn = ttk.Button(search_frame, text="开始搜索并拦截URL", command=self._start_google_search);
        self.search_btn.pack(pady=5, fill=tk.X)
        crawl_frame = ttk.LabelFrame(control_frame, text="模块 2: 全站分析", padding=10);
        crawl_frame.pack(fill=tk.X, pady=5)
        ttk.Label(crawl_frame, text="起始URL (模块1成功后自动填充):").pack(anchor='w');
        self.crawl_url_entry = ttk.Entry(crawl_frame);
        self.crawl_url_entry.pack(fill=tk.X);
        self.crawl_url_entry.insert(0, "https://adcloaking.com/")
        self.crawl_btn = ttk.Button(crawl_frame, text="爬取并分析GA标记", command=self._start_crawling);
        self.crawl_btn.pack(pady=5, fill=tk.X)
        sim_frame = ttk.LabelFrame(control_frame, text="模块 3: GA流量模拟", padding=10);
        sim_frame.pack(fill=tk.X, pady=5, expand=True)
        ttk.Label(sim_frame, text="GA Measurement ID (TID):").pack(anchor='w');
        self.tid_entry = ttk.Entry(sim_frame);
        self.tid_entry.pack(fill=tk.X);
        self.tid_entry.insert(0, "G-JE4Q4MYB64")
        ttk.Label(sim_frame, text="GTM Hash:").pack(anchor='w');
        self.gtm_entry = ttk.Entry(sim_frame);
        self.gtm_entry.pack(fill=tk.X);
        self.gtm_entry.insert(0, "45je57h0")
        ttk.Label(sim_frame, text="模拟会话次数:").pack(anchor='w');
        self.sessions_entry = ttk.Entry(sim_frame);
        self.sessions_entry.pack(fill=tk.X);
        self.sessions_entry.insert(0, "5")
        ttk.Label(sim_frame, text="代理池 (一行一个, 可留空):").pack(anchor='w', pady=(5, 0));
        self.proxy_text = scrolledtext.ScrolledText(sim_frame, height=4, width=38);
        self.proxy_text.pack(fill=tk.X, expand=True)
        self.sim_btn = ttk.Button(sim_frame, text="对爬虫发现的GA页面进行模拟", command=self._start_simulation);
        self.sim_btn.pack(pady=5, fill=tk.X)
        self.stop_btn = ttk.Button(control_frame, text="停止当前任务", command=self._stop_task, state='disabled');
        self.stop_btn.pack(pady=10, fill=tk.X)
        self.tree = ttk.Treeview(tree_frame, columns=('status'), show='tree headings');
        self.tree.heading('#0', text='页面URL');
        self.tree.heading('status', text='GA状态');
        self.tree.column('status', width=100, anchor='center');
        self.tree.pack(fill=tk.BOTH, expand=True);
        self.tree.tag_configure('has_ga', foreground='green');
        self.tree.tag_configure('no_ga', foreground='red')
        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD);
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _log(self, message):
        self.log_queue.put(message)

    def _process_log_queue_and_intercept(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_area.insert(tk.END, f"{message}\n");
                self.log_area.see(tk.END)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_log_queue_and_intercept)

    def _toggle_controls(self, is_running):
        state = 'disabled' if is_running else 'normal';
        self.stop_btn.config(state='normal' if is_running else 'disabled')
        for widget in [self.search_btn, self.crawl_btn, self.sim_btn]: widget.config(state=state)

    def _start_task(self, task_func, config_data):
        if self.active_thread and self.active_thread.is_alive(): messagebox.showwarning("提示",
                                                                                        "已有任务正在运行。"); return
        self.stop_event.clear();
        self._toggle_controls(True)
        self.active_thread = threading.Thread(target=task_func, args=(config_data,), daemon=True);
        self.active_thread.start()

    def _stop_task(self):
        if self.active_thread and self.active_thread.is_alive(): self._log(
            "--- [系统] 正在发送停止信号... ---"); self.stop_event.set(); self.stop_btn.config(state='disabled')

    def _task_cleanup(self, module_name):
        self._log(f"--- [模块{module_name}] 任务结束 ---");
        self.stop_event.clear();
        self.after(0, self._toggle_controls, False)

    def _update_crawl_url_entry(self, url):
        self.crawl_url_entry.delete(0, tk.END);
        self.crawl_url_entry.insert(0, url)
        self._log(f"--- [系统] 模块2的起始URL已自动更新为拦截到的原始URL ---")

    def _start_google_search(self):
        proxies = [p.strip() for p in self.proxy_text.get("1.0", tk.END).splitlines() if
                   p.strip() and not p.startswith('#')]
        config = {"keyword": self.keyword_entry.get(), "target_domain": self.domain_entry.get(),
                  "tld": self.tld_var.get(), "proxy": random.choice(proxies) if proxies else None}
        self._start_task(self._google_search_task, config)

    def _google_search_task(self, config):
        self._log(f"--- [模块1] 谷歌搜索启动 (关键词: {config['keyword']}, 地区: {config['tld']}) ---")
        if config.get('proxy'): self._log(f"[搜索] 使用代理: {config['proxy']}")

        found_url = None;
        found_event = threading.Event();
        interceptor_queue = queue.Queue()

        def url_interceptor():
            nonlocal found_url
            while not found_event.is_set():
                try:
                    message = interceptor_queue.get(timeout=1)
                    if "pre filter_search_result_urls() link:" in message:
                        pre_url_raw = message.split("pre filter_search_result_urls() link:")[1].strip()
                        if config['target_domain'] in pre_url_raw:
                            full_pre_url = urljoin(f"https://www.google.{config['tld']}/", pre_url_raw)
                            found_url = full_pre_url;
                            found_event.set();
                            break
                except (queue.Empty, IndexError):
                    continue

        try:
            yagoo_logger = logging.getLogger("yagooglesearch");
            interceptor_handler = QueueLogHandler(interceptor_queue)
            yagoo_logger.addHandler(interceptor_handler)
            interceptor_thread = threading.Thread(target=url_interceptor, daemon=True);
            interceptor_thread.start()

            client = CustomSearchClient(query=config['keyword'], tld=config['tld'], lang_html_ui='zh-CN',
                                        max_search_result_urls_to_return=50, proxy=config.get('proxy'))
            search_thread = threading.Thread(target=client.search, daemon=True);
            search_thread.start()

            self._log("[搜索] 正在执行搜索并实时拦截URL...")
            event_was_set = found_event.wait(timeout=25)

            if event_was_set:
                self._log(f"[搜索] ✓ 已成功拦截到目标原始URL!");
                self._log(f"  -> 原始URL: {found_url}")
                self.after(0, self._update_crawl_url_entry, found_url)
            else:
                self._log(f"[搜索] ✗ 在超时时间内未拦截到包含目标域名的URL。")

            found_event.set();
            interceptor_thread.join(timeout=2)
        except Exception as e:
            self._log(f"[错误] 搜索失败: {e}")
        finally:
            if 'interceptor_handler' in locals(): yagoo_logger.removeHandler(interceptor_handler)
            self._task_cleanup("1")

    # --- 模块 2 & 3 的代码与 V5.3 完全相同 ---
    def _start_crawling(self):
        config = {"start_url": self.crawl_url_entry.get().strip()};
        self._start_task(self._crawl_task, config)

    def _crawl_task(self, config):
        start_url = config['start_url']
        self._log(f"--- [模块2] 全站分析启动 ---")
        self._log(f"[分析] 初始URL (含跳转): {start_url}")
        self.after(0, self.tree.delete, *self.tree.get_children())

        # --- 步骤1: 处理重定向，获取最终的着陆页URL ---
        try:
            self._log("[分析] 正在处理重定向以获取真实着陆页...")
            headers = {'User-Agent': random.choice(USER_PROFILES)['ua']}
            # requests库会自动处理跳转，allow_redirects默认为True
            response = requests.get(start_url, headers=headers, timeout=15)

            # response.url 会保存经过所有跳转后的最终URL
            final_landing_page_url = response.url

            # response.history 列表记录了所有中间的跳转步骤
            if response.history:
                self._log("[分析] ✓ 重定向成功！")
                self._log(f"  -> 最终着陆页: {final_landing_page_url}")
            else:
                self._log("[分析] (提示) 提供的URL没有发生重定向。")

        except requests.RequestException as e:
            self._log(f"[错误] 访问初始URL失败: {e}")
            self._task_cleanup("2")
            return

        # --- 步骤2: 使用最终的URL作为“大本营”开始爬取 ---
        base_domain = urlparse(final_landing_page_url).netloc
        to_visit = [final_landing_page_url]  # 从最终URL开始爬
        visited = set()
        found_with_ga = []

        while to_visit and not self.stop_event.is_set():
            current_url = to_visit.pop(0)

            if current_url in visited or not urlparse(current_url).netloc.endswith(base_domain):
                continue

            visited.add(current_url)
            self._log(f"[分析] 正在爬取: {urlparse(current_url).path or '/'}")

            try:
                # 后续爬取使用相同的headers
                page_response = requests.get(current_url, headers=headers, timeout=10)
                if page_response.status_code != 200: continue

                html = page_response.text
                # has_ga = bool(re.search(r'gtag\.js|google-analytics\.com/analytics\.js|gtag\([\'"]config[\'"]', html))
                has_ga = bool(re.search(r'gtag\.js|googletagmanager\.com|gtag\([\'"]config[\'"]', html))
                if has_ga: found_with_ga.append(current_url)

                self.after(0, self._update_tree, current_url, has_ga)

                soup = BeautifulSoup(html, 'html.parser')
                for link in soup.find_all('a', href=True):
                    # 关键修复：使用 final_landing_page_url 作为基准来拼接相对链接
                    next_url = urljoin(final_landing_page_url, link['href'])
                    next_url, _ = urllib.parse.urldefrag(next_url)
                    if next_url not in visited and next_url not in to_visit:
                        to_visit.append(next_url)

            except requests.RequestException:
                continue
            # time.sleep(0.1)

        self.ga_pages = found_with_ga
        self._log(f"[分析] 爬取完成，共分析 {len(visited)} 页面，发现 {len(found_with_ga)} 个页面有GA标记。")
        self._task_cleanup("2")

    def _update_tree(self, url, has_ga):
        self.tree.insert('', 'end', text=url, values=("✓ 有GA" if has_ga else "✗ 无GA",),
                         tags=('has_ga' if has_ga else 'no_ga',))

    def _start_simulation(self):
        try:
            config = {"tid": self.tid_entry.get(), "gtm": self.gtm_entry.get(),
                      "num_sessions": int(self.sessions_entry.get()),
                      "proxies": [p.strip() for p in self.proxy_text.get("1.0", tk.END).splitlines() if
                                  p.strip() and not p.startswith('#')],
                      "target_pages": [self.tree.item(item, "text") for item in self.tree.get_children() if
                                       "has_ga" in self.tree.item(item, "tags")]}
            if not config['target_pages']: messagebox.showerror("错误",
                                                                "没有任何标记为 '有GA' 的页面可供模拟。请先运行模块2。"); return
        except ValueError:
            messagebox.showerror("错误", "模拟次数必须是整数。"); return
        self._start_task(self._simulation_task, config)

    def _simulation_task(self, config):
        self._log(f"--- [模块3] 高仿真流量模拟启动 (目标: {len(config['target_pages'])}个GA页面) ---")

        for i in range(config['num_sessions']):
            if self.stop_event.is_set(): break
            self._log(f"\n--- [流量] 会话 {i + 1}/{config['num_sessions']} 开始 ---")

            # 在每个新会话开始时，初始化所有会话相关的状态
            session_start_time = time.time()
            timestamp = int(session_start_time)
            profile = random.choice(USER_PROFILES)
            proxy = {'http': random.choice(config['proxies']), 'https': random.choice(config['proxies'])} if config[
                'proxies'] else None

            # 随机选择一个外部来源或直接访问
            referrer = random.choice(REFERRERS)

            # 创建本次会话唯一的客户端ID和会话ID
            cid = f"{random.randint(100000000, 999999999)}.{timestamp}"
            sid = str(timestamp)

            self._log(f"  [身份] Client ID: {cid}")
            self._log(f"  [身份] Session ID: {sid}")
            self._log(f"  [身份] 设备: {profile['ua'][:50]}...")
            self._log(f"  [身份] 来源: {referrer or 'Direct'}")

            # 模拟用户访问一个着陆页
            landing_page = random.choice(config['target_pages'])

            # 调用页面访问模拟器，它会处理页面内的一系列事件
            # 注意：我们将整个会话的状态传递下去
            session_context = {
                "cid": cid, "sid": sid, "sct": i + 1, "profile": profile,
                "proxy": proxy, "session_start_time": session_start_time,
                "event_count": 1  # 事件序列号从1开始
            }
            self._simulate_page_visit(landing_page, referrer, config, session_context)

            if i < config['num_sessions'] - 1 and not self.stop_event.is_set():
                sleep_time = random.uniform(1, 4)
                self._log(f"--- 会话结束，随机休眠 {sleep_time:.1f} 秒 ---")
                time.sleep(sleep_time)

        self._task_cleanup("3")

    def _simulate_page_visit(self, url, referrer, config, session_context):
        self._log(f"  [行为] 用户访问页面: {url.split('/')[-1] or '/'}")

        # 爬取页面以获取真实的标题
        try:
            r = requests.get(url, headers=session_context['profile']['headers'], proxies=session_context['proxy'],
                             timeout=10)
            title = BeautifulSoup(r.text, 'html.parser').title.string.strip() if r and r.ok else url
        except Exception:
            title = url

        # 1. 发送核心的 page_view 事件
        page_view_params = {'dl': url, 'dt': title}
        self._send_ga_hit('page_view', config, session_context, page_view_params, referrer)
        session_context['event_count'] += 1  # 序列号递增
        if self.stop_event.is_set(): return

        # 2. 模拟用户停留一段时间
        time.sleep(random.uniform(10, 25))
        if self.stop_event.is_set(): return

        # 3. 发送 user_engagement 事件 (通常在页面停留一段时间后触发)
        # engagement事件通常不带referrer
        engagement_params = {'dl': url, 'dt': title}
        self._send_ga_hit('user_engagement', config, session_context, engagement_params)
        session_context['event_count'] += 1
        if self.stop_event.is_set(): return

        # 4. 模拟用户滚动页面
        if random.random() > 0.3:  # 不是每个用户都会滚动到底
            time.sleep(random.uniform(5, 15))
            if self.stop_event.is_set(): return

            # 5. 发送 scroll 事件
            scroll_params = {'dl': url, 'dt': title, 'epn.percent_scrolled': '90'}
            self._send_ga_hit('scroll', config, session_context, scroll_params)
            session_context['event_count'] += 1

    def _send_ga_hit(self, event_name, config, session_context, extra_params=None, referrer=None):
        profile = session_context['profile']

        # --- 步骤1: 构建高仿真度的参数字典 ---
        params = {
            'v': '2',
            'tid': config['tid'],
            'gtm': config['gtm'],
            '_p': str(random.randint(10 ** 12, 10 ** 13 - 1)),  # 随机的页面ID
            'gcd': '13l3l3l3l1l1',  # Google Consent Data (可根据需要修改)
            'npa': '0',  # Non-Personalized Ads
            'dma': '0',  # DMA (Digital Markets Act) parameters
            'cid': session_context['cid'],
            'ul': 'zh-cn',
            'sr': '1920x1080',
            # --- 以下是根据您捕获的数据新增或修正的参数 ---
            'uaa': 'x86',  # User-Agent Architecture
            'uab': '64',  # User-Agent Bitness
            'uamb': '0',  # User-Agent Model: empty for non-mobile
            'uam': '',  # User-Agent Model
            'uap': 'Windows',  # User-Agent Platform
            'uapv': '10.0.0',  # User-Agent Platform Version
            'uaw': '0',  # User-Agent WOW64
            '_s': str(session_context['event_count']),  # 事件序列号
            'sid': session_context['sid'],  # 会话ID
            'sct': str(session_context['sct']),  # 会话计数
            'seg': '1',  # Session Engaged Flag
            'en': event_name,  # 事件名称
            '_ee': '1'  # E-commerce event flag? Let's keep it.
        }

        # 动态计算 TFD (Time From Display)
        tfd = int((time.time() - session_context['session_start_time']) * 1000)
        params['tfd'] = str(tfd)

        # 处理页面信息和来源
        if extra_params:
            params.update(extra_params)

        # 只有page_view事件的第一次点击才带有外部来源
        if referrer and event_name == 'page_view':
            params['dr'] = referrer

        # --- 步骤2: 构建高仿真度的头部 ---
        origin_url = params.get('dl', 'https://adcloaking.com/')
        origin = urlparse(origin_url).scheme + "://" + urlparse(origin_url).netloc

        headers = {
            'User-Agent': profile['ua'],
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Origin': origin,
            'Referer': origin + '/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
        }
        # 合并来自USER_PROFILES的Sec-Ch-Ua头部
        headers.update(profile['headers'])

        # --- 步骤3: 发送请求 ---
        full_url = f"https://www.google-analytics.com/g/collect?{urllib.parse.urlencode(params)}"
        self.proxy_dict = {
            "http": "",
            "https": ""
        }
        try:
            #r = requests.post(full_url, headers=headers, proxies=session_context['proxy'], timeout=15, verify=False)
            r = requests.post(full_url, headers=headers, proxies=self.proxy_dict, timeout=15, verify=False)
            self._log(
                f"    -> GA事件 '{event_name}' {'发送成功' if r.status_code == 204 else f'发送失败, 状态码: {r.status_code}'}")
        except Exception as e:
            self._log(f"    -> [错误] GA事件发送失败: {e}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
