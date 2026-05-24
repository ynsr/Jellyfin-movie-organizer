# Task Title:

## Task Description:

When searching using search.bertina.ir (mostly searching for www.doostiha.com for example `https://search.bertina.ir/search?q=Luke+and+Lucy+The+Texas+Rangers+2009+site%3Awww.doostihaa.com`), The link is relative, not direct link (similar to `/api/click?dest=aHR0cHM6Ly93d3cuZG9vc3RpaGFhLmNvbS9wb3N0L3RhZy8lRDglQUYlRDglQ...`) with HTTP redirects. Instead, use `cite` html tag of first `article` tag to find the actual result link.

Sample `article` result of Bertina search engine:
```html
<article class="group animate-fade-in pb-6" style="animation-delay:0ms"><div class="flex items-center gap-2 text-sm"><span class="relative inline-flex items-center gap-1.5"><span class="relative inline-block"><img src="/api/favicon/aaa2bcc9d3789b55c252f3a4f9a7ffd5" alt="" width="16" height="16" class="flex-shrink-0 rounded-sm transition-opacity duration-200" loading="lazy"><span data-testid="ir-access-dot" aria-hidden="true" class="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full ring-1 ring-white" title="این سایت از داخل ایران بدون فیلترشکن باز می‌شود" style="background-color: rgb(22, 163, 74);"></span></span><span data-testid="ir-access-pill" dir="rtl" class="inline-flex items-center rounded px-1 py-px text-[9px] font-medium text-white whitespace-nowrap" title="این سایت از داخل ایران بدون فیلترشکن باز می‌شود" style="background-color: rgb(22, 163, 74);">بازمیشه</span></span><cite class="not-italic text-[var(--url-green)] line-clamp-1" dir="ltr" title="https://www.doostihaa.com/post/tag/%D8%AF%D8%A7%D9%86%D9%84%D9%88%D8%AF-%D8%A7%D9%86%DB%8C%D9%85%DB%8C%D8%B4%D9%86-luke-and-lucy-the-texas-rangers-%D8%A8%D8%A7-%DA%A9%DB%8C%D9%81%DB%8C%D8%AA-1080p">www.doostihaa.com/post/tag/دانلود-انیمیشن-luke-and-lucy-the-texa...</cite></div><h3 class="mt-1"><a href="/api/click?dest=aHR0cHM6Ly93d3cuZG9vc3RpaGFhLmNvbS9wb3N0L3RhZy8lRDglQUYlRDglQTclRDklODYlRDklODQlRDklODglRDglQUYtJUQ4JUE3JUQ5JTg2JURCJThDJUQ5JTg1JURCJThDJUQ4JUI0JUQ5JTg2LWx1a2UtYW5kLWx1Y3ktdGhlLXRleGFzLXJhbmdlcnMtJUQ4JUE4JUQ4JUE3LSVEQSVBOSVEQiU4QyVEOSU4MSVEQiU4QyVEOCVBQS0xMDgwcA&amp;t=organic&amp;q=Luke+and+Lucy+The+Texas+Rangers+2009+site%3Awww.doostihaa.com&amp;pos=1&amp;pg=1&amp;sid=1779664190945-a4muhncv1&amp;cid=1779664193370-wyh9rob" target="_blank" rel="noopener noreferrer" class="text-xl font-normal text-[var(--link-blue)] hover:underline visited:text-[var(--link-visited)] line-clamp-2">دانلود انیمیشن Luke and Lucy The Texas Rangers با کیفیت 1080p</a></h3><p class="mt-1 text-sm leading-relaxed text-[var(--text-secondary)] line-clamp-3">دانلود رایگان انیمیشن باب و بابت Luke and Lucy: The Texas Rangers 2009 BluRay ... خلاصه داستان: لوک و لوسی (به فرانسوی: باب و بابت) دو دوست جدانشدنی هستند که باید ...</p></article>
```

## Context:

- Related Files/Resources:
  - [bertina.py](src/scrapers/bertina.py)
