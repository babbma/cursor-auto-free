import os
import platform
import json
import sys
from colorama import Fore, Style
from enum import Enum
from typing import Optional

from exit_cursor import ExitCursor
import go_cursor_help
import patch_cursor_get_machine_id
from reset_machine import MachineIDResetter
from language import language, get_translation
from openpyxl import Workbook

os.environ["PYTHONVERBOSE"] = "0"
os.environ["PYINSTALLER_VERBOSE"] = "0"

import time
import random
from cursor_auth_manager import CursorAuthManager
import os
from logger import logging
from browser_utils import BrowserManager
from get_email_code import EmailVerificationHandler
from logo import print_logo
from config import Config
from datetime import datetime

# Define EMOJI dictionary
EMOJI = {"ERROR": get_translation("error"), "WARNING": get_translation("warning"), "INFO": get_translation("info")}


class VerificationStatus(Enum):
    """Verification status enum"""

    PASSWORD_PAGE = "@name=password"
    CAPTCHA_PAGE = "@data-index=0"
    ACCOUNT_SETTINGS = "Account Settings"


class TurnstileError(Exception):
    """Turnstile verification related exception"""

    pass


def save_screenshot(tab, stage: str, timestamp: bool = True) -> None:
    """
    Save a screenshot of the page

    Args:
        tab: Browser tab object
        stage: Stage identifier for the screenshot
        timestamp: Whether to add a timestamp
    """
    try:
        # Create screenshots directory
        screenshot_dir = "screenshots"
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)

        # Generate filename
        if timestamp:
            filename = f"turnstile_{stage}_{int(time.time())}.png"
        else:
            filename = f"turnstile_{stage}.png"

        filepath = os.path.join(screenshot_dir, filename)

        # Save screenshot
        tab.get_screenshot(filepath)
        logging.debug(f"Screenshot saved: {filepath}")
    except Exception as e:
        logging.warning(f"Failed to save screenshot: {str(e)}")


def check_verification_success(tab) -> Optional[VerificationStatus]:
    """
    Check if verification was successful

    Returns:
        VerificationStatus: The corresponding status if successful, None if failed
    """
    for status in VerificationStatus:
        if tab.ele(status.value):
            logging.info(get_translation("verification_success", status=status.name))
            return status
    return None


def handle_turnstile(tab, max_retries: int = 2, retry_interval: tuple = (1, 2)) -> bool:
    """
    Handle Turnstile verification

    Args:
        tab: Browser tab object
        max_retries: Maximum number of retries
        retry_interval: Retry interval range (min, max)

    Returns:
        bool: Whether verification was successful

    Raises:
        TurnstileError: Exception during verification process
    """
    logging.info(get_translation("detecting_turnstile"))
    save_screenshot(tab, "start")

    retry_count = 0

    try:
        while retry_count < max_retries:
            retry_count += 1
            logging.debug(get_translation("retry_verification", count=retry_count))

            try:
                # Locate verification frame element
                challenge_check = (
                    tab.ele("@id=cf-turnstile", timeout=2)
                    .child()
                    .shadow_root.ele("tag:iframe")
                    .ele("tag:body")
                    .sr("tag:input")
                )
                '''
                  challenge_check = (tab.ele("@id=wBIvQ7", timeout=2)
                                       .child()
                                       .child()
                                       .shadow_root.ele("tag:iframe").ele("tag:body")
                                        .shadow_root
                                       .sr("tag:input"))
                                       '''

                if challenge_check:
                    logging.info(get_translation("detected_turnstile"))
                    # Random delay before clicking verification
                    time.sleep(random.uniform(1, 3))
                    challenge_check.click()
                    time.sleep(2)

                    # Save screenshot after verification
                    save_screenshot(tab, "clicked")

                    # Check verification result
                    if check_verification_success(tab):
                        logging.info(get_translation("turnstile_verification_passed"))
                        save_screenshot(tab, "success")
                        return True

            except Exception as e:
                logging.debug(f"Current attempt unsuccessful: {str(e)}")

            # Check if already verified
            if check_verification_success(tab):
                return True

            # Random delay before next attempt
            time.sleep(random.uniform(*retry_interval))

        # Exceeded maximum retries
        logging.error(get_translation("verification_failed_max_retries", max_retries=max_retries))
        logging.error(
            "Please visit the open source project for more information: https://github.com/chengazhen/cursor-auto-free"
        )
        save_screenshot(tab, "failed")
        return False

    except Exception as e:
        error_msg = get_translation("turnstile_exception", error=str(e))
        logging.error(error_msg)
        save_screenshot(tab, "error")
        raise TurnstileError(error_msg)


def get_cursor_session_token(tab, max_attempts=3, retry_interval=2):
    """
    Get Cursor session token with retry mechanism
    :param tab: Browser tab
    :param max_attempts: Maximum number of attempts
    :param retry_interval: Retry interval (seconds)
    :return: Session token or None
    """
    logging.info(get_translation("getting_cookie"))
    attempts = 0

    while attempts < max_attempts:
        try:
            cookies = tab.cookies()
            for cookie in cookies:
                if cookie.get("name") == "WorkosCursorSessionToken":
                    return cookie["value"].split("%3A%3A")[1]

            attempts += 1
            if attempts < max_attempts:
                logging.warning(
                    get_translation("cookie_attempt_failed", attempts=attempts, retry_interval=retry_interval)
                )
                time.sleep(retry_interval)
            else:
                logging.error(
                    get_translation("cookie_max_attempts", max_attempts=max_attempts)
                )

        except Exception as e:
            logging.error(get_translation("cookie_failure", error=str(e)))
            attempts += 1
            if attempts < max_attempts:
                logging.info(get_translation("retry_in_seconds", seconds=retry_interval))
                time.sleep(retry_interval)

    return None


def update_cursor_auth(email=None, access_token=None, refresh_token=None):
    """
    Update Cursor authentication information
    """
    auth_manager = CursorAuthManager()
    return auth_manager.update_auth(email, access_token, refresh_token)


def sign_up_account(browser, tab):
    logging.info(get_translation("start_account_registration"))
    logging.info(get_translation("visiting_registration_page", url=sign_up_url))
    sign_button = tab.ele('xpath://a[@class=\'cursor-pointer hover:underline text-sk-sea/70\']')
    if sign_button:
        sign_button.click()
    else:
        tab.get(sign_up_url)
    #tab.ele('xpath://*[@id="eIfwt6"]/div/div').sr('tag:iframe').ele('tag:body').sr('tag:input').click()
    if not tab.ele("@name=first_name"):
        result =input('是否已经在注册的页面')
        if result == 'y':
            pass

    try:
        if tab.ele("@name=first_name"):
            logging.info(get_translation("filling_personal_info"))
            tab.actions.click("@name=firstName").input(first_name)
            logging.info(get_translation("input_first_name", name=first_name))
            time.sleep(random.uniform(1, 3))

            tab.actions.click("@name=lastName").input(last_name)
            logging.info(get_translation("input_last_name", name=last_name))
            time.sleep(random.uniform(1, 3))

            tab.actions.click("@name=email").input(account)
            logging.info(get_translation("input_email", email=account))
            time.sleep(random.uniform(1, 3))

            tab.actions.click("@name=agreeTOS")
            time.sleep(random.uniform(1, 3))
            
            logging.info(get_translation("submitting_personal_info"))
            tab.actions.click("@@type=button@@text=Continue")

    except Exception as e:
        logging.error(get_translation("registration_page_access_failed", error=str(e)))
        return False

    handle_turnstile(tab)

    try:
        if tab.ele("@name=password"):
            logging.info(get_translation("setting_password"))
            tab.ele("@name=password").input(password)
            time.sleep(random.uniform(1, 3))

            logging.info(get_translation("submitting_password"))
            tab.ele("@type=submit").click()
            logging.info(get_translation("password_setup_complete"))

    except Exception as e:
        logging.error(get_translation("password_setup_failed", error=str(e)))
        return False

    if tab.ele("This email is not available."):
        logging.error(get_translation("registration_failed_email_used"))
        return False

    handle_turnstile(tab)

    while True:
        try:
            if tab.ele("Account Settings"):
                logging.info(get_translation("registration_success"))
                break
            if tab.ele("@data-index=0"):
                logging.info(get_translation("getting_email_verification"))
                code = email_handler.get_verification_code()
                if not code:
                    logging.error(get_translation("verification_code_failure"))
                    return False

                logging.info(get_translation("verification_code_success", code=code))
                logging.info(get_translation("inputting_verification_code"))
                i = 0
                for digit in code:
                    tab.ele(f"@data-index={i}").input(digit)
                    time.sleep(random.uniform(0.1, 0.3))
                    i += 1
                logging.info(get_translation("verification_code_input_complete"))
                break
        except Exception as e:
            logging.error(get_translation("verification_code_process_error", error=str(e)))

    handle_turnstile(tab)
    wait_time = random.randint(3, 6)
    for i in range(wait_time):
        logging.info(get_translation("waiting_system_processing", seconds=wait_time-i))
        time.sleep(1)

    logging.info(get_translation("getting_account_info"))
    tab.get(settings_url)
    try:
        usage_selector = (
            "css:div.col-span-2 > div > div > div > div > "
            "div:nth-child(1) > div.flex.items-center.justify-between.gap-2 > "
            "span.font-mono.text-sm\\/\\[0\\.875rem\\]"
        )
        usage_ele = tab.ele(usage_selector)
        if usage_ele:
            usage_info = usage_ele.text
            total_usage = usage_info.split("/")[-1].strip()
            logging.info(get_translation("account_usage_limit", limit=total_usage))
            logging.info(
                "Please visit the open source project for more information: https://github.com/chengazhen/cursor-auto-free"
            )
    except Exception as e:
        logging.error(get_translation("account_usage_info_failure", error=str(e)))

    logging.info(get_translation("registration_complete"))
    account_info = get_translation("cursor_account_info", email=account, password=password)
    logging.info(account_info)
    time.sleep(5)
    return True


class EmailGenerator:
    def __init__(
        self,
        password="".join(
            random.choices(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*",
                k=12,
            )
        ),
    ):
        configInstance = Config()
        configInstance.print_config()
        self.domain = configInstance.get_domain()
        self.names = self.load_names()
        self.default_password = password
        self.default_first_name = self.generate_random_name()
        self.default_last_name = self.generate_random_name()

    def load_names(self):
        try:
            with open("names-dataset.txt", "r") as file:
                return file.read().split()
        except FileNotFoundError:
            logging.warning(get_translation("names_file_not_found"))
            # Fallback to a small set of default names if the file is not found
            return ["John", "Jane", "Alex", "Emma", "Michael", "Olivia", "William", "Sophia", 
                    "James", "Isabella", "Robert", "Mia", "David", "Charlotte", "Joseph", "Amelia"]

    def generate_random_name(self):
        """Generate a random username"""
        return random.choice(self.names)

    def generate_email(self, length=4):
        """Generate a random, unique-ish email address"""
        length = max(4, length)
        # 使用纳秒时间戳 + 2 位随机字符，避免在快速循环中重复
        suffix = str(time.time_ns())[-length:] + ''.join(
            random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=2)
        )
        return f"{self.default_first_name}{suffix}@{self.domain}"

    def get_account_info(self):
        """Get complete account information"""
        return {
            "email": self.generate_email(),
            "password": self.default_password,
            "first_name": self.default_first_name,
            "last_name": self.default_last_name,
        }


def get_user_agent():
    """Get user_agent"""
    try:
        # Use JavaScript to get user agent
        browser_manager = BrowserManager()
        browser = browser_manager.init_browser()
        user_agent = browser.latest_tab.run_js("return navigator.userAgent")
        browser_manager.quit()
        return user_agent
    except Exception as e:
        logging.error(f"Failed to get user agent: {str(e)}")
        return None


def check_cursor_version():
    """Check cursor version"""
    pkg_path, main_path = patch_cursor_get_machine_id.get_cursor_paths()
    with open(pkg_path, "r", encoding="utf-8") as f:
        version = json.load(f)["version"]
    return patch_cursor_get_machine_id.version_check(version, min_version="0.45.0")


def reset_machine_id(greater_than_0_45):
    if greater_than_0_45:
        # Prompt to manually execute script https://github.com/chengazhen/cursor-auto-free/blob/main/patch_cursor_get_machine_id.py
        go_cursor_help.go_cursor_help()
    else:
        MachineIDResetter().reset_machine_ids()


def print_end_message():
    logging.info("\n\n\n\n\n")
    logging.info("=" * 30)
    logging.info(get_translation("all_operations_completed"))
    logging.info("\n=== Get More Information ===")
    logging.info("📺 Bilibili UP: 想回家的前端")
    logging.info("🔥 WeChat Official Account: code 未来")
    logging.info("=" * 30)
    logging.info(
        "Please visit the open source project for more information: https://github.com/chengazhen/cursor-auto-free"
    )


def export_accounts_to_xlsx(rows, filename: str = "") -> str:
    """将账号信息导出为 xlsx 文件。

    rows: 列表，每项为包含 first_name、last_name、email、password、token、status 的字典
    filename: 可选自定义路径；为空则默认写入 logs/accounts_时间戳.xlsx
    返回最终写入的文件路径
    """
    if not filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join("logs", f"accounts_{ts}.xlsx")

    # 确保目录存在
    dir_path = os.path.dirname(filename)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "accounts"
    header = ["first_name", "last_name", "email", "password", "token", "status"]
    ws.append(header)

    for r in rows:
        ws.append([
            r.get("first_name", ""),
            r.get("last_name", ""),
            r.get("email", ""),
            r.get("password", ""),
            r.get("token", ""),
            r.get("status", ""),
        ])

    wb.save(filename)
    logging.info(f"Accounts exported to: {filename}")
    return filename


def run_registration_flow(account_info: dict):
    """执行一次完整注册流程，返回 (token, status)。
    status: 'success' 或 'failed'
    """
    # 这些变量在 sign_up_account 中会被引用
    global first_name, last_name, account, password, email_handler
    global sign_up_url

    first_name = account_info["first_name"]
    last_name = account_info["last_name"]
    account = account_info["email"]
    password = account_info["password"]
    email_handler = EmailVerificationHandler(account)

    # 站点配置放到模块全局，供 sign_up_account 使用
    login_url = "https://windsurf.com/account/login"
    sign_up_url = "https://windsurf.com/account/register"
    # settings_url = "https://www.cursor.com/settings"

    logging.info(get_translation("generating_random_account"))
    logging.info(get_translation("generated_email_account", email=account))
    logging.info(get_translation("initializing_browser"))

    # 获取并规范化 UA
    user_agent = get_user_agent()
    if not user_agent:
        logging.error(get_translation("get_user_agent_failed"))
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    user_agent = user_agent.replace("HeadlessChrome", "Chrome")

    browser_manager = None
    token_value = ""
    status_value = "failed"
    try:
        browser_manager = BrowserManager()
        browser = browser_manager.init_browser(user_agent)

        logging.info(
            "Please visit the open source project for more information: https://github.com/chengazhen/cursor-auto-free"
        )
        logging.info(get_translation("configuration_info"))

        tab = browser.latest_tab
        tab.run_js("try { turnstile.reset() } catch(e) { }")

        logging.info(get_translation("starting_registration"))
        logging.info(get_translation("visiting_login_page", url=login_url))
        tab.get(login_url)

        if sign_up_account(browser, tab):
            logging.info(get_translation("getting_session_token"))
            token = get_cursor_session_token(tab)
            if token:
                logging.info(get_translation("updating_auth_info"))
                update_cursor_auth(email=account, access_token=token, refresh_token=token)
                token_value = token
                status_value = "success"
                logging.info(
                    "Please visit the open source project for more information: https://github.com/chengazhen/cursor-auto-free"
                )
                logging.info(get_translation("resetting_machine_code"))
                reset_machine_id(greater_than_0_45)
                logging.info(get_translation("all_operations_completed"))
                print_end_message()
            else:
                logging.error(get_translation("session_token_failed"))
    except Exception as e:
        logging.error(get_translation("program_error", error=str(e)))
    finally:
        if browser_manager:
            browser_manager.quit()
        time.sleep(1)

    return token_value, status_value

if __name__ == "__main__":
    print_logo()
    
    # Add language selection
    print("\n")
    language.select_language_prompt()
    
    browser_manager = None
    try:
        logging.info(get_translation("initializing_program"))
        # ExitCursor()
        try:
            greater_than_0_45 = check_cursor_version()
        except Exception:
            greater_than_0_45 = False

        # Prompt user to select operation mode
        print(get_translation("select_operation_mode"))
        print(get_translation("menu_full_registration"))
        print(get_translation("menu_batch_generate_accounts"))
        print(get_translation("menu_batch_full_registration"))

        while True:
            try:
                choice = int(input(get_translation("enter_option_3")).strip())
                if choice in [1, 2,3]:
                    break
                else:
                    print(get_translation("invalid_option"))
            except ValueError:
                print(get_translation("enter_valid_number"))

        email_generator = EmailGenerator()
        results = []
        if choice == 2 or choice == 3:
            try:
                count = int(input(get_translation("enter_batch_count")).strip())
            except ValueError:
                print(get_translation("enter_valid_number"))
                sys.exit(1)
            for _ in range(count):
                info = email_generator.get_account_info()
                results.append({
                    "first_name": info["first_name"],
                    "last_name": info["last_name"],
                    "email": info["email"],
                    "password": info["password"],
                    "token": "",
                    "status": "generated",
                })
                time.sleep(random.uniform(0.2, 0.6))
            if choice == 2:
                export_accounts_to_xlsx(results)
                sys.exit(0)

        if choice == 3:
            for account in results:
                token_value, status_value = run_registration_flow(account)
                results.append({
                    "first_name": account["first_name"],
                    "last_name": account["last_name"],
                    "email": account["email"],
                    "password": account["password"],
                    "token": token_value,
                    "status": status_value,
                })

            export_accounts_to_xlsx(results)
            sys.exit(0)

        # 单次完整注册流程：复用通用方法，避免重复代码
        single_info = email_generator.get_account_info()
        run_registration_flow(single_info)

    except Exception as e:
        logging.error(get_translation("program_error", error=str(e)))
    finally:
        if browser_manager:
            browser_manager.quit()
        input(get_translation("program_exit_message"))
