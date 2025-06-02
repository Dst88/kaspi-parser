import re
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

LANG = {
    'ru': {
        'title': "Парсер Kaspi.kz",
        'url_label': "Введите URL каталога:",
        'start': "Начать парсинг",
        'stop': "Остановить парсинг",
        'save_as': "Формат сохранения:",
        'log_label': "Логи:",
        'error_url': "Пожалуйста, введите корректный URL!",
        'done_msg': "Парсинг завершён. Данные сохранены.",
        'stopped_msg': "Парсинг остановлен пользователем.",
    }
}

current_lang = 'ru'
stop_parsing = False

def log_message(log_widget, message):
    log_widget.config(state='normal')
    log_widget.insert(tk.END, f"{message}\n")
    log_widget.see(tk.END)
    log_widget.config(state='disabled')

def parse_product_details(driver, link, log_widget):
    specifications_list, seller_columns, price_columns = [], [], []
    additional_dict = {}
    try:
        driver.execute_script("window.open('', '_blank');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(link)
        time.sleep(1)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        for element in soup.find_all('ul', class_='short-specifications'):
            for spec in element.find_all('li', class_='short-specifications__text'):
                specifications_list.append(spec.text.strip())
        try:
            next_button = driver.find_elements(By.XPATH, '//li[contains(@class, "tabs-content__tab") and contains(text(), "Характеристики")]')
            if next_button:
                driver.execute_script("arguments[0].click();", next_button[0])
                time.sleep(1)
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                for el in soup.find_all('dl', class_='specifications-list__el'):
                    for spec in el.find_all('dl', class_='specifications-list__spec'):
                        term = spec.find('span', class_='specifications-list__spec-term-text')
                        val = spec.find('dd', class_='specifications-list__spec-definition')
                        if term and val:
                            additional_dict[term.text.strip()] = val.text.strip()
        except: pass

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        sellers_table = soup.find('table', class_='sellers-table__self')
        unique_sellers = set()
        if sellers_table:
            for row in sellers_table.find_all('tr'):
                link = row.find('a', href=True)
                if link:
                    name = link.text.strip()
                    price_el = row.find('div', class_='sellers-table__price-cell-text')
                    price = re.sub(r'\s+', ' ', price_el.text.replace('\xa0', '')) if price_el else None
                    if name not in unique_sellers:
                        seller_columns.append(name)
                        price_columns.append(price)
                        unique_sellers.add(name)

        specifications_dict = {}
        for spec in specifications_list:
            if ':' in spec:
                k, v = spec.split(':', 1)
                specifications_dict[k.strip()] = v.strip()

        driver.close()
        driver.switch_to.window(driver.window_handles[0])

        result = {**specifications_dict, **additional_dict}
        for i in range(min(len(seller_columns), len(price_columns), 6)):
            result[f"Seller_{i + 1}"] = seller_columns[i]
            result[f"Price_{i + 1}"] = price_columns[i]
        return result
    except Exception as e:
        log_message(log_widget, f"Ошибка парсинга товара: {e}")
        try:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
        except: pass
        return {}

def run_scraper(url, log_widget, start_btn, stop_btn, format_var, progress_bar):
    global stop_parsing
    stop_parsing = False

    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--user-agent=Mozilla/5.0")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    data = []

    progress_bar.grid()  # Показать прогресс-бар
    progress_bar.start(10)  # Запустить анимацию

    try:
        driver.get(url)
    except Exception as e:
        log_message(log_widget, f"Ошибка загрузки: {e}")
        start_btn.config(state='normal')
        stop_btn.config(state='disabled')
        progress_bar.stop()
        progress_bar.grid_remove()
        driver.quit()
        return

    page_num = 1
    while True:
        if stop_parsing:
            log_message(log_widget, LANG[current_lang]['stopped_msg'])
            break

        time.sleep(1)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        products = soup.find_all(class_='item-card__info')
        if not products:
            break
        for product in products:
            if stop_parsing:
                break
            try:
                title = product.find(class_='item-card__name').text.strip()
                rel_link = product.find('a', class_='item-card__name-link')['href']
                link = f"https://kaspi.kz{rel_link}"
                price = product.find('span', class_='item-card__prices-price').text.strip()
                rating_el = product.find(class_='item-card__rating')
                rating = rating_el.text.strip() if rating_el else 'Нет рейтинга'

                product_data = {
                    'Название': title,
                    'Ссылка': link,
                    'Цена': price,
                    'Рейтинг': rating,
                    **parse_product_details(driver, link, log_widget),
                }
                data.append(product_data)
                log_message(log_widget, f"Собран товар: {title}")
            except Exception as e:
                log_message(log_widget, f"Ошибка: {e}")

        try:
            next_button = driver.find_elements(By.XPATH, '//li[contains(@class, "pagination__el") and contains(text(), "Следующая")]')
            if next_button and 'disabled' not in next_button[0].get_attribute('class'):
                driver.execute_script("arguments[0].click();", next_button[0])
                page_num += 1
                time.sleep(2)
            else:
                log_message(log_widget, "Достигнута последняя страница.")
                break
        except:
            break

    progress_bar.stop()
    progress_bar.grid_remove()

    if data:
        df = pd.DataFrame(data)
        try:
            fmt = format_var.get()
            file_path = filedialog.asksaveasfilename(defaultextension=f".{fmt}", filetypes=[(fmt.upper(), f"*.{fmt}")])
            if file_path:
                if fmt == 'xlsx':
                    df.to_excel(file_path, index=False)
                elif fmt == 'csv':
                    df.to_csv(file_path, index=False)
                elif fmt == 'json':
                    df.to_json(file_path, orient='records', force_ascii=False)
                log_message(log_widget, LANG[current_lang]['done_msg'])
        except Exception as e:
            log_message(log_widget, f"Ошибка сохранения: {e}")
    else:
        log_message(log_widget, "Нет данных для сохранения.")

    start_btn.config(state='normal')
    stop_btn.config(state='disabled')
    driver.quit()

def start_thread(url_entry, log_widget, start_btn, stop_btn, format_var, progress_bar):
    url = url_entry.get().strip()
    if not url.startswith('http'):
        messagebox.showerror("Ошибка", LANG[current_lang]['error_url'])
        return
    start_btn.config(state='disabled')
    stop_btn.config(state='normal')
    threading.Thread(target=run_scraper, args=(url, log_widget, start_btn, stop_btn, format_var, progress_bar), daemon=True).start()

def stop_parsing_callback():
    global stop_parsing
    stop_parsing = True

def build_ui():
    root = tk.Tk()
    root.title(LANG[current_lang]['title'])
    root.geometry('980x720')
    root.configure(bg="#2E3440")  # Тёмный фон (Norse Night)

    style = ttk.Style()
    style.theme_use('clam')

    # Настроим цвета для виджетов
    style.configure('TLabel', background="#2E3440", foreground="#D8DEE9", font=("Segoe UI", 11))
    style.configure('TButton', font=("Segoe UI", 11, 'bold'), padding=8,
                    background="#5E81AC", foreground="#ECEFF4")
    style.map('TButton',
              background=[('active', '#81A1C1'), ('disabled', '#4C566A')],
              foreground=[('disabled', '#D8DEE9')])
    style.configure('TEntry', padding=8, foreground="#2E3440", fieldbackground="#D8DEE9")
    style.configure('TRadiobutton', background="#2E3440", foreground="#D8DEE9", font=("Segoe UI", 10))

    container = ttk.Frame(root, padding=25, style='TFrame')
    container.pack(fill='both', expand=True)

    # Заголовок
    title_label = ttk.Label(container, text=LANG[current_lang]['title'],
                            font=("Segoe UI", 18, 'bold'))
    title_label.grid(row=0, column=0, sticky='w', pady=(0, 20))

    # URL Label + Entry
    ttk.Label(container, text=LANG[current_lang]['url_label'], font=("Segoe UI", 12, "bold")).grid(row=1, column=0, sticky='w')
    url_entry = ttk.Entry(container, width=110)
    url_entry.grid(row=2, column=0, sticky='we', pady=(5, 20))
    url_entry.insert(0, "https://kaspi.kz/shop/semey/c/smart%20glasses/?q=%3Acategory%3ASmart%20glasses%3AavailableInZones%3A632810000&sort=relevance&sc=")

    # Формат сохранения
    format_frame = ttk.Frame(container, style='TFrame')
    format_frame.grid(row=3, column=0, sticky='w', pady=(0, 15))
    ttk.Label(format_frame, text=LANG[current_lang]['save_as'], font=("Segoe UI", 12, "bold")).pack(side='left')
    format_var = tk.StringVar(value='xlsx')
    for fmt in ['xlsx', 'csv', 'json']:
        ttk.Radiobutton(format_frame, text=fmt.upper(), variable=format_var, value=fmt).pack(side='left', padx=15)

    # Кнопки
    button_frame = ttk.Frame(container, style='TFrame')
    button_frame.grid(row=4, column=0, sticky='w', pady=(0, 20))
    start_btn = ttk.Button(button_frame, text=LANG[current_lang]['start'],
                           command=lambda: start_thread(url_entry, log_text, start_btn, stop_btn, format_var, progress_bar))
    start_btn.pack(side='left', padx=(0, 15), ipadx=10, ipady=5)
    stop_btn = ttk.Button(button_frame, text=LANG[current_lang]['stop'],
                          command=stop_parsing_callback, state='disabled')
    stop_btn.pack(side='left', ipadx=10, ipady=5)

    # Прогресс-бар (скрыт пока)
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(container, variable=progress_var, maximum=100, mode='indeterminate')
    progress_bar.grid(row=5, column=0, sticky='we', pady=(0, 15))
    progress_bar.grid_remove()

    # Лог с рамкой и тёмным фоном
    log_frame = ttk.Frame(container)
    log_frame.grid(row=6, column=0, sticky='nsew')
    log_text = tk.Text(log_frame, height=25, state='disabled', wrap='word',
                       font=("Consolas", 11), bg="#3B4252", fg="#D8DEE9", relief='sunken', bd=2, padx=8, pady=6)
    log_text.pack(side='left', fill='both', expand=True)
    scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=log_text.yview)
    scrollbar.pack(side='right', fill='y')
    log_text.config(yscrollcommand=scrollbar.set)

    container.columnconfigure(0, weight=1)
    container.rowconfigure(6, weight=1)

    root.mainloop()

if __name__ == "__main__":
    build_ui()
