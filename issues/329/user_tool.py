import sys, os

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, base_path)

import pytest_asyncio
import pytest
import logging
import sys

from playwright.async_api import async_playwright, expect
from utils.email_handler import EmailHandler
from utils.trace_cleaner import trace_cleaner

from io import BytesIO
from PIL import Image


NEWDOT_URL = "https://dev.new.expensify.com:8082/"
OLDDOT_URL = "http://localhost:9000/"
EXPENSIFY_EMAIL = "testingq186@gmail.com"
EXPENSIFY_PASSWORD = ""


logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
LOGGER = logging.getLogger(__name__)

def create_dummy_image():
    img = Image.new('RGB', (100, 100), color='red')
    byte_io = BytesIO()
    img.save(byte_io, 'PNG')
    byte_io.seek(0)
    return byte_io


TESTING_FLOW = True


@pytest_asyncio.fixture
async def page():
    """
    Launch the Expensify app.
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(channel="chrome", headless=True, args=["--ignore-certificate-errors", "--disable-web-security", "--disable-features=IsolateOrigins,site-per-process"], proxy={"server": "http://localhost:8080"}, slow_mo=500)
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()

    yield page

    # Original cleanup (if browser is still open, this may be a redundant close if already closed in test)
    await browser.close()
    await pw.stop()


@pytest.mark.asyncio
async def test_the_issue(page):
    """
    Demonstrate the Expensify app email login verification with tracing.
    """
    await page.goto(NEWDOT_URL)

    # Start tracing using the page context
    context = page.context
    await context.tracing.start(screenshots=True, snapshots=True, sources=True)

    try:
        with EmailHandler(EXPENSIFY_EMAIL, EXPENSIFY_PASSWORD) as email_handler:
            if not TESTING_FLOW:
                email_handler.clean_inbox()  # Clean inbox

            await page.get_by_role("textbox", name="Phone or email").fill(EXPENSIFY_EMAIL)
            await page.get_by_role("button", name="Continue").click()

            otp = email_handler.read_otp_code() if not TESTING_FLOW else "123456"
            await page.locator('input[name="validateCode"]').first.fill(otp)

            await page.get_by_text("Please enter the magic code").wait_for(state="hidden")
            logging.info("Sign in complete.")
        
        await page.locator('div[aria-label="Start chat (Floating action)"]').last.click()
        await page.locator('text="Request money"').click()
        await page.locator('text="Manual"').last.click()
        await page.locator('input[placeholder="0"]').fill("200")
        await page.keyboard.press("Enter")
        await page.locator('input[aria-label="Name, email, or phone number"]').fill("test1@gmail.com")
        await page.locator('div[aria-label="test1@gmail.com"]').last.click()
        await page.locator('div[aria-label="More"]').last.click()
        await page.locator('text="Add receipt"').last.click()
        
        dummy_image = create_dummy_image()
        async with page.expect_file_chooser() as fc_info:
            await page.locator('text="Choose file"').last.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files([{ 
                "name": "dummy_image.png",
                "mimeType": "image/png",
                "buffer": dummy_image.getvalue()
            }])
        two_100_dollar = page.get_by_role("button", name="Request").filter(has_text="200.0")
        
        await expect(two_100_dollar).to_be_visible()
    finally:
        # Stop tracing and export the trace file
        trace_path = "/app/expensify/user_tool/output_browser1.zip"
        await context.tracing.stop(path=trace_path)
        trace_cleaner(trace_path)
        
        # Close the browser
        await page.context.browser.close()