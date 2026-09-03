package dev.chanwoo.rhodesreader;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.PopupMenu;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Rhodes Reader KR
 *
 * A small Android shell optimized for the Korean Arknights Story Text Reader.
 * The story content remains hosted by the upstream project; this app adds Android-native
 * reading conveniences such as persistent position, bookmarks, zoom and safe link handling.
 */
public class MainActivity extends Activity {
    private static final String HOME_URL = "https://050644zf.github.io/ArknightsStoryTextReader/#/ko_KR/menu";
    private static final String PREFS = "rhodes_reader_prefs";
    private static final String KEY_LAST_URL = "last_url";
    private static final String KEY_TEXT_ZOOM = "text_zoom";
    private static final String KEY_KEEP_AWAKE = "keep_awake";
    private static final String KEY_BOOKMARKS = "bookmarks";
    private static final String KEY_SCROLL_PREFIX = "scroll::";
    private static final long AUTOSAVE_INTERVAL_MS = 5000L;

    private WebView webView;
    private ProgressBar progressBar;
    private TextView pageTitle;
    private Button bookmarkButton;
    private SharedPreferences prefs;
    private final Handler handler = new Handler(Looper.getMainLooper());

    private final Runnable autosaveRunnable = new Runnable() {
        @Override
        public void run() {
            persistCurrentReadingState();
            handler.postDelayed(this, AUTOSAVE_INTERVAL_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        applyKeepAwake();
        buildUi();
        configureWebView();

        String startUrl = prefs.getString(KEY_LAST_URL, HOME_URL);
        if (startUrl == null || startUrl.trim().isEmpty() || !isAllowedReaderUrl(startUrl)) {
            startUrl = HOME_URL;
        }
        webView.loadUrl(startUrl);
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(17, 19, 24));

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setOrientation(LinearLayout.HORIZONTAL);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(8), dp(6), dp(8), dp(6));
        toolbar.setBackgroundColor(Color.rgb(17, 19, 24));

        Button back = toolbarButton("‹");
        back.setContentDescription("뒤로");
        back.setOnClickListener(v -> navigateBack());
        toolbar.addView(back, buttonParams());

        Button home = toolbarButton("⌂");
        home.setContentDescription("한국 서버 홈");
        home.setOnClickListener(v -> {
            persistCurrentReadingState();
            webView.loadUrl(HOME_URL);
        });
        toolbar.addView(home, buttonParams());

        pageTitle = new TextView(this);
        pageTitle.setText("Rhodes Reader KR");
        pageTitle.setTextColor(Color.WHITE);
        pageTitle.setTextSize(15);
        pageTitle.setSingleLine(true);
        pageTitle.setPadding(dp(10), 0, dp(8), 0);
        toolbar.addView(pageTitle, new LinearLayout.LayoutParams(0, dp(44), 1f));

        bookmarkButton = toolbarButton("☆");
        bookmarkButton.setContentDescription("북마크");
        bookmarkButton.setOnClickListener(v -> toggleCurrentBookmark());
        bookmarkButton.setOnLongClickListener(v -> {
            showBookmarks();
            return true;
        });
        toolbar.addView(bookmarkButton, buttonParams());

        Button more = toolbarButton("⋮");
        more.setContentDescription("더보기");
        more.setOnClickListener(this::showMoreMenu);
        toolbar.addView(more, buttonParams());

        root.addView(toolbar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        root.addView(progressBar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(2)));

        webView = new WebView(this);
        root.addView(webView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        setContentView(root);
    }

    private void configureWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(true);
        s.setTextZoom(prefs.getInt(KEY_TEXT_ZOOM, 100));
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setUserAgentString(s.getUserAgentString() + " RhodesReaderKR/1.0.0");

        webView.setBackgroundColor(Color.rgb(17, 19, 24));
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }

            @Override
            public void onReceivedTitle(WebView view, String title) {
                if (title != null && !title.trim().isEmpty()) pageTitle.setText(title);
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme();
                String host = uri.getHost();

                if ("https".equalsIgnoreCase(scheme) && host != null && isInternalHost(host)) {
                    persistCurrentReadingState();
                    return false;
                }

                openExternal(uri);
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                if (url != null && isAllowedReaderUrl(url)) {
                    prefs.edit().putString(KEY_LAST_URL, url).apply();
                    restoreScroll(url);
                    updateBookmarkButton();
                }
            }
        });
    }

    private boolean isInternalHost(String host) {
        return host.equals("050644zf.github.io") || host.equals("astr.pages.dev");
    }

    private boolean isAllowedReaderUrl(String url) {
        try {
            Uri uri = Uri.parse(url);
            return "https".equalsIgnoreCase(uri.getScheme())
                    && uri.getHost() != null
                    && isInternalHost(uri.getHost());
        } catch (Exception ignored) {
            return false;
        }
    }

    private void openExternal(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (Exception e) {
            Toast.makeText(this, "외부 링크를 열 수 없어", Toast.LENGTH_SHORT).show();
        }
    }

    private void showMoreMenu(View anchor) {
        PopupMenu menu = new PopupMenu(this, anchor);
        menu.getMenu().add("북마크 목록");
        menu.getMenu().add("글자 크기");
        menu.getMenu().add("화면 계속 켜기");
        menu.getMenu().add("새로고침");
        menu.getMenu().add("현재 페이지 공유");
        menu.getMenu().add("한국 서버 홈");
        menu.getMenu().add("웹 캐시 비우기");

        menu.setOnMenuItemClickListener(item -> {
            String title = item.getTitle().toString();
            switch (title) {
                case "북마크 목록": showBookmarks(); return true;
                case "글자 크기": showTextZoomDialog(); return true;
                case "화면 계속 켜기": toggleKeepAwake(); return true;
                case "새로고침": webView.reload(); return true;
                case "현재 페이지 공유": shareCurrentPage(); return true;
                case "한국 서버 홈":
                    persistCurrentReadingState();
                    webView.loadUrl(HOME_URL);
                    return true;
                case "웹 캐시 비우기":
                    webView.clearCache(true);
                    Toast.makeText(this, "웹 캐시를 비웠어", Toast.LENGTH_SHORT).show();
                    return true;
                default: return false;
            }
        });
        menu.show();
    }

    private void showTextZoomDialog() {
        String[] labels = {"작게 85%", "기본 100%", "크게 115%", "아주 크게 130%"};
        int[] values = {85, 100, 115, 130};
        int current = prefs.getInt(KEY_TEXT_ZOOM, 100);
        int selected = 1;
        for (int i = 0; i < values.length; i++) {
            if (values[i] == current) selected = i;
        }

        new AlertDialog.Builder(this)
                .setTitle("글자 크기")
                .setSingleChoiceItems(labels, selected, (dialog, which) -> {
                    int zoom = values[which];
                    prefs.edit().putInt(KEY_TEXT_ZOOM, zoom).apply();
                    webView.getSettings().setTextZoom(zoom);
                    dialog.dismiss();
                })
                .setNegativeButton("취소", null)
                .show();
    }

    private void toggleKeepAwake() {
        boolean next = !prefs.getBoolean(KEY_KEEP_AWAKE, false);
        prefs.edit().putBoolean(KEY_KEEP_AWAKE, next).apply();
        applyKeepAwake();
        Toast.makeText(this,
                next ? "읽는 동안 화면을 켜둘게" : "화면 자동 꺼짐을 다시 허용했어",
                Toast.LENGTH_SHORT).show();
    }

    private void applyKeepAwake() {
        boolean keep = prefs.getBoolean(KEY_KEEP_AWAKE, false);
        if (keep) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    private void shareCurrentPage() {
        String url = webView.getUrl();
        if (url == null) return;
        Intent send = new Intent(Intent.ACTION_SEND);
        send.setType("text/plain");
        send.putExtra(Intent.EXTRA_TEXT, url);
        startActivity(Intent.createChooser(send, "스토리 링크 공유"));
    }

    private void toggleCurrentBookmark() {
        String url = webView.getUrl();
        if (url == null || url.equals(HOME_URL)) {
            Toast.makeText(this, "스토리/이벤트 페이지에서 북마크해줘", Toast.LENGTH_SHORT).show();
            return;
        }

        LinkedHashMap<String, String> bookmarks = loadBookmarks();
        if (bookmarks.containsKey(url)) {
            bookmarks.remove(url);
            saveBookmarks(bookmarks);
            Toast.makeText(this, "북마크에서 뺐어", Toast.LENGTH_SHORT).show();
        } else {
            String title = webView.getTitle();
            if (title == null || title.trim().isEmpty()) title = url;
            bookmarks.put(url, title);
            saveBookmarks(bookmarks);
            Toast.makeText(this, "북마크했어 ★", Toast.LENGTH_SHORT).show();
        }
        updateBookmarkButton();
    }

    private LinkedHashMap<String, String> loadBookmarks() {
        LinkedHashMap<String, String> map = new LinkedHashMap<>();
        try {
            JSONArray array = new JSONArray(prefs.getString(KEY_BOOKMARKS, "[]"));
            for (int i = 0; i < array.length(); i++) {
                JSONObject object = array.getJSONObject(i);
                map.put(object.getString("url"), object.optString("title", object.getString("url")));
            }
        } catch (Exception ignored) { }
        return map;
    }

    private void saveBookmarks(LinkedHashMap<String, String> map) {
        JSONArray array = new JSONArray();
        try {
            for (Map.Entry<String, String> entry : map.entrySet()) {
                JSONObject object = new JSONObject();
                object.put("url", entry.getKey());
                object.put("title", entry.getValue());
                array.put(object);
            }
            prefs.edit().putString(KEY_BOOKMARKS, array.toString()).apply();
        } catch (Exception ignored) { }
    }

    private void updateBookmarkButton() {
        if (bookmarkButton == null || webView == null) return;
        String url = webView.getUrl();
        boolean bookmarked = url != null && loadBookmarks().containsKey(url);
        bookmarkButton.setText(bookmarked ? "★" : "☆");
    }

    private void showBookmarks() {
        LinkedHashMap<String, String> bookmarks = loadBookmarks();
        if (bookmarks.isEmpty()) {
            new AlertDialog.Builder(this)
                    .setTitle("북마크")
                    .setMessage("아직 저장한 페이지가 없어.\n상단 ☆ 버튼을 눌러 추가하면 돼.")
                    .setPositiveButton("확인", null)
                    .show();
            return;
        }

        ArrayList<String> urls = new ArrayList<>(bookmarks.keySet());
        ArrayList<String> titles = new ArrayList<>(bookmarks.values());
        String[] items = titles.toArray(new String[0]);

        new AlertDialog.Builder(this)
                .setTitle("북마크")
                .setItems(items, (dialog, which) -> {
                    persistCurrentReadingState();
                    webView.loadUrl(urls.get(which));
                })
                .setNeutralButton("전체 삭제", (dialog, which) -> {
                    prefs.edit().putString(KEY_BOOKMARKS, "[]").apply();
                    updateBookmarkButton();
                    Toast.makeText(this, "북마크를 전부 지웠어", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("닫기", null)
                .show();
    }

    private void persistCurrentReadingState() {
        if (webView == null) return;
        String url = webView.getUrl();
        if (url == null || !isAllowedReaderUrl(url)) return;
        prefs.edit().putString(KEY_LAST_URL, url).apply();
        saveScroll(url);
    }

    private void saveScroll(String url) {
        webView.evaluateJavascript(
                "Math.round(window.scrollY || document.documentElement.scrollTop || 0)",
                value -> {
                    try {
                        int y = Integer.parseInt(value.replace("\"", ""));
                        prefs.edit().putInt(KEY_SCROLL_PREFIX + url, y).apply();
                    } catch (Exception ignored) { }
                });
    }

    private void restoreScroll(String url) {
        int y = prefs.getInt(KEY_SCROLL_PREFIX + url, 0);
        if (y <= 0) return;
        handler.postDelayed(() -> {
            if (webView != null) {
                webView.evaluateJavascript("window.scrollTo(0," + y + ")", null);
            }
        }, 550);
    }

    private void navigateBack() {
        persistCurrentReadingState();
        if (webView.canGoBack()) webView.goBack();
        else webView.loadUrl(HOME_URL);
    }

    @Override
    public void onBackPressed() {
        persistCurrentReadingState();
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onPause() {
        handler.removeCallbacks(autosaveRunnable);
        if (webView != null) {
            persistCurrentReadingState();
            webView.onPause();
        }
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) webView.onResume();
        handler.removeCallbacks(autosaveRunnable);
        handler.postDelayed(autosaveRunnable, AUTOSAVE_INTERVAL_MS);
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        if (webView != null) {
            persistCurrentReadingState();
            webView.stopLoading();
            webView.setWebChromeClient(null);
            webView.setWebViewClient(null);
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    private Button toolbarButton(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(20);
        button.setTextColor(Color.WHITE);
        button.setAllCaps(false);
        button.setGravity(Gravity.CENTER);
        button.setPadding(0, 0, 0, 0);
        button.setBackgroundColor(Color.TRANSPARENT);
        return button;
    }

    private LinearLayout.LayoutParams buttonParams() {
        return new LinearLayout.LayoutParams(dp(46), dp(44));
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
    }
}
