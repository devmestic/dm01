package dev.chanwoo.rhodesreader;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.PopupMenu;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;

/**
 * Rhodes Reader KR v2
 *
 * Fully offline native reader. Story JSON files are packaged in the APK at build time.
 * No WebView and no INTERNET permission are used.
 */
public class MainActivity extends Activity {
    private static final String PREFS = "rhodes_reader_native";
    private static final String KEY_TEXT_SCALE = "text_scale";
    private static final String KEY_KEEP_AWAKE = "keep_awake";
    private static final String KEY_BOOKMARKS = "bookmarks";
    private static final String KEY_LAST_STORY = "last_story";
    private static final String KEY_POS_PREFIX = "pos::";

    private static final int BG = Color.rgb(17, 19, 24);
    private static final int PANEL = Color.rgb(27, 30, 37);
    private static final int PANEL_2 = Color.rgb(34, 38, 46);
    private static final int TEXT = Color.rgb(239, 242, 247);
    private static final int MUTED = Color.rgb(164, 173, 186);
    private static final int ACCENT = Color.rgb(102, 192, 255);

    private SharedPreferences prefs;
    private final ArrayList<StoryEntry> allStories = new ArrayList<>();
    private final ArrayList<EventGroup> eventGroups = new ArrayList<>();
    private final ArrayList<StoryEntry> visibleStories = new ArrayList<>();

    private LinearLayout root;
    private TextView titleView;
    private Button bookmarkButton;
    private ProgressBar progressBar;
    private EditText searchBox;
    private ListView listView;

    private Screen screen = Screen.LIBRARY;
    private EventGroup currentEvent;
    private StoryEntry currentStory;
    private StoryLineAdapter currentLineAdapter;

    private enum Screen { LIBRARY, EVENT, SEARCH, READER }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        applyKeepAwake();
        buildBaseUi();
        loadIndex();
    }

    private void buildBaseUi() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(BG);
        setContentView(root);
        showLibraryShell("Rhodes Reader KR");
    }

    private void showLibraryShell(String title) {
        root.removeAllViews();

        LinearLayout toolbar = createToolbar(title, false);
        root.addView(toolbar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        searchBox = new EditText(this);
        searchBox.setHint("스토리 · 이벤트 · 작전명 검색");
        searchBox.setHintTextColor(MUTED);
        searchBox.setTextColor(TEXT);
        searchBox.setSingleLine(true);
        searchBox.setTextSize(16);
        searchBox.setBackgroundColor(PANEL);
        searchBox.setPadding(dp(14), dp(8), dp(14), dp(8));
        LinearLayout.LayoutParams searchParams = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(50));
        searchParams.setMargins(dp(10), dp(8), dp(10), dp(8));
        root.addView(searchBox, searchParams);

        progressBar = new ProgressBar(this);
        root.addView(progressBar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(3)));

        listView = new ListView(this);
        listView.setDividerHeight(1);
        listView.setBackgroundColor(BG);
        listView.setCacheColorHint(BG);
        root.addView(listView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        searchBox.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {
                if (allStories.isEmpty()) return;
                String q = s.toString().trim();
                if (q.isEmpty()) {
                    screen = Screen.LIBRARY;
                    showEventGroups();
                } else {
                    screen = Screen.SEARCH;
                    showSearchResults(q);
                }
            }
            @Override public void afterTextChanged(Editable s) {}
        });
    }

    private LinearLayout createToolbar(String title, boolean reader) {
        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setOrientation(LinearLayout.HORIZONTAL);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(6), dp(5), dp(6), dp(5));
        toolbar.setBackgroundColor(PANEL);

        if (screen != Screen.LIBRARY || reader) {
            Button back = toolbarButton("‹");
            back.setContentDescription("뒤로");
            back.setOnClickListener(v -> navigateBack());
            toolbar.addView(back, buttonParams());
        }

        titleView = new TextView(this);
        titleView.setText(title);
        titleView.setTextColor(TEXT);
        titleView.setTextSize(reader ? 15 : 17);
        titleView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        titleView.setSingleLine(true);
        titleView.setPadding(dp(10), 0, dp(8), 0);
        toolbar.addView(titleView, new LinearLayout.LayoutParams(0, dp(46), 1f));

        if (reader) {
            bookmarkButton = toolbarButton(isBookmarked(currentStory.path) ? "★" : "☆");
            bookmarkButton.setContentDescription("북마크");
            bookmarkButton.setOnClickListener(v -> toggleBookmark());
            toolbar.addView(bookmarkButton, buttonParams());
        }

        Button more = toolbarButton("⋮");
        more.setOnClickListener(v -> showMoreMenu(v, reader));
        toolbar.addView(more, buttonParams());
        return toolbar;
    }

    private void loadIndex() {
        progressBar.setVisibility(View.VISIBLE);
        new Thread(() -> {
            try {
                JSONObject rootJson = new JSONObject(readAsset("story_index.json"));
                JSONArray items = rootJson.getJSONArray("stories");
                ArrayList<StoryEntry> loaded = new ArrayList<>();
                for (int i = 0; i < items.length(); i++) {
                    JSONObject o = items.getJSONObject(i);
                    StoryEntry e = new StoryEntry();
                    e.path = o.optString("path");
                    e.eventId = o.optString("eventId");
                    e.eventName = blankTo(o.optString("eventName"), "기타 스토리");
                    e.entryType = blankTo(o.optString("entryType"), "STORY");
                    e.storyCode = o.optString("storyCode");
                    e.avgTag = o.optString("avgTag");
                    e.storyName = blankTo(o.optString("storyName"), e.storyCode);
                    e.storyInfo = o.optString("storyInfo");
                    loaded.add(e);
                }
                runOnUiThread(() -> {
                    allStories.clear();
                    allStories.addAll(loaded);
                    buildEventGroups();
                    progressBar.setVisibility(View.GONE);
                    showEventGroups();
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    progressBar.setVisibility(View.GONE);
                    showFatal("오프라인 스토리 인덱스를 읽지 못했어.\n" + e.getMessage());
                });
            }
        }).start();
    }

    private void buildEventGroups() {
        eventGroups.clear();
        LinkedHashMap<String, EventGroup> map = new LinkedHashMap<>();
        for (StoryEntry story : allStories) {
            String key = story.entryType + "\u0000" + story.eventId + "\u0000" + story.eventName;
            EventGroup group = map.get(key);
            if (group == null) {
                group = new EventGroup();
                group.key = key;
                group.eventName = story.eventName;
                group.entryType = story.entryType;
                group.eventId = story.eventId;
                map.put(key, group);
            }
            group.stories.add(story);
        }
        eventGroups.addAll(map.values());
    }

    private void showEventGroups() {
        if (listView == null) return;
        titleView.setText("Rhodes Reader KR · " + allStories.size() + "편");
        EventAdapter adapter = new EventAdapter(this, eventGroups);
        listView.setAdapter(adapter);
        listView.setOnItemClickListener((parent, view, position, id) -> {
            currentEvent = eventGroups.get(position);
            openEvent(currentEvent);
        });
    }

    private void showSearchResults(String query) {
        visibleStories.clear();
        String q = query.toLowerCase(Locale.ROOT);
        for (StoryEntry e : allStories) {
            if (e.searchText().contains(q)) visibleStories.add(e);
        }
        titleView.setText("검색 · " + visibleStories.size() + "편");
        StoryAdapter adapter = new StoryAdapter(this, visibleStories);
        listView.setAdapter(adapter);
        listView.setOnItemClickListener((parent, view, position, id) -> openStory(visibleStories.get(position)));
    }

    private void openEvent(EventGroup group) {
        screen = Screen.EVENT;
        root.removeAllViews();
        root.addView(createToolbar(group.eventName, false), new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        TextView meta = new TextView(this);
        meta.setText(group.entryType + " · " + group.stories.size() + "편");
        meta.setTextColor(MUTED);
        meta.setTextSize(13);
        meta.setPadding(dp(16), dp(10), dp(16), dp(10));
        root.addView(meta);

        listView = new ListView(this);
        listView.setBackgroundColor(BG);
        listView.setDividerHeight(1);
        listView.setAdapter(new StoryAdapter(this, group.stories));
        listView.setOnItemClickListener((parent, view, position, id) -> openStory(group.stories.get(position)));
        root.addView(listView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
    }

    private void openStory(StoryEntry story) {
        currentStory = story;
        prefs.edit().putString(KEY_LAST_STORY, story.path).apply();
        screen = Screen.READER;

        root.removeAllViews();
        root.addView(createToolbar(displayStoryTitle(story), true), new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setPadding(dp(16), dp(12), dp(16), dp(12));
        header.setBackgroundColor(PANEL_2);

        TextView event = text(story.eventName, 13, ACCENT);
        event.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        header.addView(event);

        if (!story.storyInfo.trim().isEmpty()) {
            TextView info = text(story.storyInfo.trim(), 13, MUTED);
            info.setPadding(0, dp(7), 0, 0);
            header.addView(info);
        }
        root.addView(header);

        progressBar = new ProgressBar(this);
        root.addView(progressBar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(3)));

        listView = new ListView(this);
        listView.setBackgroundColor(BG);
        listView.setDividerHeight(0);
        root.addView(listView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        loadStory(story);
    }

    private void loadStory(StoryEntry story) {
        progressBar.setVisibility(View.VISIBLE);
        new Thread(() -> {
            try {
                JSONObject json = new JSONObject(readAsset("story/" + story.path));
                JSONArray storyList = json.getJSONArray("storyList");
                ArrayList<ReaderLine> lines = parseStoryLines(storyList);
                runOnUiThread(() -> {
                    progressBar.setVisibility(View.GONE);
                    currentLineAdapter = new StoryLineAdapter(this, lines, prefs.getInt(KEY_TEXT_SCALE, 100));
                    listView.setAdapter(currentLineAdapter);
                    restoreReaderPosition(story.path);
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    progressBar.setVisibility(View.GONE);
                    showFatal("스토리 파일을 읽지 못했어.\n" + story.path + "\n" + e.getMessage());
                });
            }
        }).start();
    }

    private ArrayList<ReaderLine> parseStoryLines(JSONArray source) {
        ArrayList<ReaderLine> out = new ArrayList<>();
        for (int i = 0; i < source.length(); i++) {
            JSONObject line = source.optJSONObject(i);
            if (line == null) continue;
            String prop = line.optString("prop").toLowerCase(Locale.ROOT);
            JSONObject a = line.optJSONObject("attributes");
            if (a == null) a = new JSONObject();

            if (prop.equals("name") || prop.equals("multiline")) {
                String content = clean(a.optString("content"));
                if (!content.isEmpty()) out.add(ReaderLine.dialog(clean(a.optString("name")), content));
                continue;
            }
            if (prop.equals("subtitle") || prop.equals("sticker")) {
                String content = clean(a.optString("text"));
                if (content.isEmpty()) content = clean(a.optString("content"));
                if (!content.isEmpty()) out.add(ReaderLine.center(content));
                continue;
            }
            if (prop.equals("decision")) {
                String optionsRaw = a.optString("options");
                if (!optionsRaw.isEmpty()) {
                    out.add(ReaderLine.note("선택지"));
                    String[] options = optionsRaw.split(";");
                    for (String option : options) {
                        String t = clean(option);
                        if (!t.isEmpty()) out.add(ReaderLine.choice(t));
                    }
                }
                continue;
            }
            if (prop.equals("predicate")) {
                String refs = a.optString("references");
                if (!refs.isEmpty()) out.add(ReaderLine.note("분기 · " + refs.replace(';', ' · ')));
                continue;
            }
            if (prop.equals("comment")) {
                String value = clean(a.optString("value"));
                if (!value.isEmpty()) out.add(ReaderLine.note(value));
                continue;
            }

            String content = clean(a.optString("content"));
            if (content.isEmpty()) content = clean(a.optString("text"));
            if (!content.isEmpty()) out.add(ReaderLine.center(content));
        }
        return out;
    }

    private void showMoreMenu(View anchor, boolean reader) {
        PopupMenu menu = new PopupMenu(this, anchor);
        if (reader) {
            menu.getMenu().add("글자 크기");
            menu.getMenu().add("처음으로");
            menu.getMenu().add("이벤트 목록");
        } else {
            String last = prefs.getString(KEY_LAST_STORY, "");
            if (!last.isEmpty()) menu.getMenu().add("마지막 읽던 스토리");
            menu.getMenu().add("북마크 목록");
        }
        menu.getMenu().add("화면 계속 켜기");
        menu.getMenu().add("앱 정보");

        menu.setOnMenuItemClickListener(item -> {
            String title = item.getTitle().toString();
            switch (title) {
                case "글자 크기": showTextScaleDialog(); return true;
                case "처음으로":
                    if (listView != null) listView.setSelection(0);
                    return true;
                case "이벤트 목록":
                    showLibrary();
                    return true;
                case "마지막 읽던 스토리":
                    openLastStory();
                    return true;
                case "북마크 목록":
                    showBookmarks();
                    return true;
                case "화면 계속 켜기":
                    toggleKeepAwake();
                    return true;
                case "앱 정보":
                    showAbout();
                    return true;
                default: return false;
            }
        });
        menu.show();
    }

    private void showTextScaleDialog() {
        String[] labels = {"작게 85%", "기본 100%", "크게 115%", "아주 크게 130%"};
        int[] values = {85, 100, 115, 130};
        int current = prefs.getInt(KEY_TEXT_SCALE, 100);
        int selected = 1;
        for (int i = 0; i < values.length; i++) if (values[i] == current) selected = i;
        new AlertDialog.Builder(this)
                .setTitle("글자 크기")
                .setSingleChoiceItems(labels, selected, (dialog, which) -> {
                    prefs.edit().putInt(KEY_TEXT_SCALE, values[which]).apply();
                    dialog.dismiss();
                    if (currentStory != null) {
                        saveReaderPosition();
                        openStory(currentStory);
                    }
                })
                .setNegativeButton("취소", null)
                .show();
    }

    private void toggleBookmark() {
        if (currentStory == null) return;
        LinkedHashMap<String, Boolean> marks = readBookmarks();
        boolean adding = !marks.containsKey(currentStory.path);
        if (adding) marks.put(currentStory.path, true); else marks.remove(currentStory.path);
        writeBookmarks(marks);
        bookmarkButton.setText(adding ? "★" : "☆");
        Toast.makeText(this, adding ? "북마크에 추가했어" : "북마크에서 뺐어", Toast.LENGTH_SHORT).show();
    }

    private boolean isBookmarked(String path) {
        return readBookmarks().containsKey(path);
    }

    private LinkedHashMap<String, Boolean> readBookmarks() {
        LinkedHashMap<String, Boolean> result = new LinkedHashMap<>();
        String raw = prefs.getString(KEY_BOOKMARKS, "[]");
        try {
            JSONArray a = new JSONArray(raw);
            for (int i = 0; i < a.length(); i++) result.put(a.getString(i), true);
        } catch (Exception ignored) {}
        return result;
    }

    private void writeBookmarks(LinkedHashMap<String, Boolean> marks) {
        JSONArray a = new JSONArray();
        for (String path : marks.keySet()) a.put(path);
        prefs.edit().putString(KEY_BOOKMARKS, a.toString()).apply();
    }

    private void showBookmarks() {
        LinkedHashMap<String, Boolean> marks = readBookmarks();
        visibleStories.clear();
        for (StoryEntry e : allStories) if (marks.containsKey(e.path)) visibleStories.add(e);
        if (visibleStories.isEmpty()) {
            Toast.makeText(this, "아직 북마크가 없어", Toast.LENGTH_SHORT).show();
            return;
        }
        screen = Screen.SEARCH;
        root.removeAllViews();
        root.addView(createToolbar("북마크 · " + visibleStories.size() + "편", false));
        listView = new ListView(this);
        listView.setBackgroundColor(BG);
        listView.setAdapter(new StoryAdapter(this, visibleStories));
        listView.setOnItemClickListener((parent, view, position, id) -> openStory(visibleStories.get(position)));
        root.addView(listView, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
    }

    private void openLastStory() {
        String path = prefs.getString(KEY_LAST_STORY, "");
        for (StoryEntry e : allStories) {
            if (e.path.equals(path)) {
                openStory(e);
                return;
            }
        }
        Toast.makeText(this, "저장된 마지막 스토리를 찾지 못했어", Toast.LENGTH_SHORT).show();
    }

    private void saveReaderPosition() {
        if (screen != Screen.READER || currentStory == null || listView == null) return;
        int pos = listView.getFirstVisiblePosition();
        int top = 0;
        View child = listView.getChildAt(0);
        if (child != null) top = child.getTop();
        prefs.edit().putString(KEY_POS_PREFIX + currentStory.path, pos + "," + top).apply();
    }

    private void restoreReaderPosition(String path) {
        String raw = prefs.getString(KEY_POS_PREFIX + path, "");
        if (raw.isEmpty()) return;
        try {
            String[] p = raw.split(",", 2);
            int pos = Integer.parseInt(p[0]);
            int top = Integer.parseInt(p[1]);
            listView.post(() -> listView.setSelectionFromTop(pos, top));
        } catch (Exception ignored) {}
    }

    private void toggleKeepAwake() {
        boolean enabled = !prefs.getBoolean(KEY_KEEP_AWAKE, true);
        prefs.edit().putBoolean(KEY_KEEP_AWAKE, enabled).apply();
        applyKeepAwake();
        Toast.makeText(this, enabled ? "읽는 동안 화면을 계속 켜둘게" : "화면 자동 꺼짐을 허용했어", Toast.LENGTH_SHORT).show();
    }

    private void applyKeepAwake() {
        boolean enabled = prefs.getBoolean(KEY_KEEP_AWAKE, true);
        if (enabled) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }

    private void showAbout() {
        new AlertDialog.Builder(this)
                .setTitle("Rhodes Reader KR 2.0.0")
                .setMessage("완전 오프라인 네이티브 명일방주 한국어 스토리 리더\n\nWebView 없음 · 인터넷 권한 없음\n스토리 데이터는 APK 내부 assets에 포함됨\n\n스토리 데이터 출처: 050644zf/ArknightsStoryJson")
                .setPositiveButton("확인", null)
                .show();
    }

    private void navigateBack() {
        if (screen == Screen.READER) {
            saveReaderPosition();
            if (currentEvent != null && currentEvent.stories.contains(currentStory)) openEvent(currentEvent);
            else showLibrary();
            return;
        }
        if (screen == Screen.EVENT || screen == Screen.SEARCH) {
            showLibrary();
            return;
        }
        finish();
    }

    private void showLibrary() {
        saveReaderPosition();
        currentStory = null;
        currentEvent = null;
        screen = Screen.LIBRARY;
        showLibraryShell("Rhodes Reader KR");
        if (!allStories.isEmpty()) {
            progressBar.setVisibility(View.GONE);
            showEventGroups();
        }
    }

    @Override
    public void onBackPressed() {
        if (screen == Screen.LIBRARY) super.onBackPressed(); else navigateBack();
    }

    @Override
    protected void onPause() {
        saveReaderPosition();
        super.onPause();
    }

    private String readAsset(String path) throws Exception {
        try (InputStream in = getAssets().open(path); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[16384];
            int n;
            while ((n = in.read(buf)) >= 0) out.write(buf, 0, n);
            return out.toString(StandardCharsets.UTF_8.name());
        }
    }

    private String displayStoryTitle(StoryEntry s) {
        String left = (s.storyCode + " " + s.avgTag).trim();
        if (left.isEmpty()) return s.storyName;
        return left + " · " + s.storyName;
    }

    private void showFatal(String message) {
        new AlertDialog.Builder(this)
                .setTitle("Rhodes Reader KR")
                .setMessage(message)
                .setPositiveButton("확인", null)
                .show();
    }

    private Button toolbarButton(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setTextSize(21);
        b.setTextColor(TEXT);
        b.setBackgroundColor(Color.TRANSPARENT);
        b.setPadding(0, 0, 0, 0);
        return b;
    }

    private LinearLayout.LayoutParams buttonParams() {
        return new LinearLayout.LayoutParams(dp(48), dp(46));
    }

    private TextView text(String value, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setLineSpacing(0, 1.25f);
        return t;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    private static String blankTo(String s, String fallback) {
        return s == null || s.trim().isEmpty() ? fallback : s;
    }

    private static String clean(String s) {
        if (s == null) return "";
        return s.replace("\\n", "\n").replaceAll("^[\\s　]+|[\\s　]+$", "");
    }

    private static final class StoryEntry {
        String path, eventId, eventName, entryType, storyCode, avgTag, storyName, storyInfo;
        String searchText() {
            return (eventName + " " + entryType + " " + storyCode + " " + avgTag + " " + storyName + " " + storyInfo)
                    .toLowerCase(Locale.ROOT);
        }
    }

    private static final class EventGroup {
        String key, eventId, eventName, entryType;
        final ArrayList<StoryEntry> stories = new ArrayList<>();
    }

    private static final class ReaderLine {
        static final int DIALOG = 0;
        static final int CENTER = 1;
        static final int CHOICE = 2;
        static final int NOTE = 3;
        final int type;
        final String speaker;
        final String content;
        ReaderLine(int type, String speaker, String content) {
            this.type = type;
            this.speaker = speaker;
            this.content = content;
        }
        static ReaderLine dialog(String speaker, String content) { return new ReaderLine(DIALOG, speaker, content); }
        static ReaderLine center(String content) { return new ReaderLine(CENTER, "", content); }
        static ReaderLine choice(String content) { return new ReaderLine(CHOICE, "", content); }
        static ReaderLine note(String content) { return new ReaderLine(NOTE, "", content); }
    }

    private static final class EventAdapter extends BaseAdapter {
        private final Context context;
        private final List<EventGroup> groups;
        EventAdapter(Context c, List<EventGroup> groups) { this.context = c; this.groups = groups; }
        @Override public int getCount() { return groups.size(); }
        @Override public Object getItem(int position) { return groups.get(position); }
        @Override public long getItemId(int position) { return position; }
        @Override public View getView(int position, View convertView, ViewGroup parent) {
            EventGroup g = groups.get(position);
            LinearLayout row = new LinearLayout(context);
            row.setOrientation(LinearLayout.VERTICAL);
            row.setPadding(dp(context, 16), dp(context, 13), dp(context, 16), dp(context, 13));
            row.setBackgroundColor(position % 2 == 0 ? BG : Color.rgb(20, 23, 29));
            TextView name = makeText(context, g.eventName, 16, TEXT);
            name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            row.addView(name);
            TextView meta = makeText(context, g.entryType + " · " + g.stories.size() + "편", 12, MUTED);
            meta.setPadding(0, dp(context, 4), 0, 0);
            row.addView(meta);
            return row;
        }
    }

    private static final class StoryAdapter extends BaseAdapter {
        private final Context context;
        private final List<StoryEntry> stories;
        StoryAdapter(Context c, List<StoryEntry> stories) { this.context = c; this.stories = stories; }
        @Override public int getCount() { return stories.size(); }
        @Override public Object getItem(int position) { return stories.get(position); }
        @Override public long getItemId(int position) { return position; }
        @Override public View getView(int position, View convertView, ViewGroup parent) {
            StoryEntry s = stories.get(position);
            LinearLayout row = new LinearLayout(context);
            row.setOrientation(LinearLayout.VERTICAL);
            row.setPadding(dp(context, 16), dp(context, 12), dp(context, 16), dp(context, 12));
            row.setBackgroundColor(position % 2 == 0 ? BG : Color.rgb(20, 23, 29));
            String code = (s.storyCode + " " + s.avgTag).trim();
            TextView name = makeText(context, (code.isEmpty() ? "" : code + " · ") + s.storyName, 15, TEXT);
            name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            row.addView(name);
            TextView event = makeText(context, s.eventName, 12, ACCENT);
            event.setPadding(0, dp(context, 4), 0, 0);
            row.addView(event);
            if (!s.storyInfo.trim().isEmpty()) {
                String info = s.storyInfo.replace('\n', ' ').trim();
                if (info.length() > 110) info = info.substring(0, 110) + "…";
                TextView desc = makeText(context, info, 12, MUTED);
                desc.setPadding(0, dp(context, 5), 0, 0);
                row.addView(desc);
            }
            return row;
        }
    }

    private static final class StoryLineAdapter extends BaseAdapter {
        private final Context context;
        private final List<ReaderLine> lines;
        private final float scale;
        StoryLineAdapter(Context c, List<ReaderLine> lines, int scalePercent) {
            this.context = c;
            this.lines = lines;
            this.scale = scalePercent / 100f;
        }
        @Override public int getCount() { return lines.size(); }
        @Override public Object getItem(int position) { return lines.get(position); }
        @Override public long getItemId(int position) { return position; }
        @Override public View getView(int position, View convertView, ViewGroup parent) {
            ReaderLine line = lines.get(position);
            LinearLayout row = new LinearLayout(context);
            row.setOrientation(LinearLayout.VERTICAL);
            row.setPadding(dp(context, 18), dp(context, 10), dp(context, 18), dp(context, 10));
            row.setBackgroundColor(BG);

            if (line.type == ReaderLine.DIALOG) {
                if (!line.speaker.isEmpty()) {
                    TextView speaker = makeText(context, line.speaker, 13 * scale, ACCENT);
                    speaker.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
                    row.addView(speaker);
                }
                TextView content = makeText(context, line.content, 17 * scale, TEXT);
                content.setLineSpacing(dp(context, 3), 1.28f);
                content.setPadding(0, line.speaker.isEmpty() ? 0 : dp(context, 4), 0, 0);
                row.addView(content);
            } else if (line.type == ReaderLine.CENTER) {
                TextView content = makeText(context, line.content, 15 * scale, Color.rgb(210, 216, 226));
                content.setGravity(Gravity.CENTER);
                content.setTypeface(Typeface.DEFAULT, Typeface.ITALIC);
                content.setPadding(dp(context, 8), dp(context, 7), dp(context, 8), dp(context, 7));
                row.addView(content);
            } else if (line.type == ReaderLine.CHOICE) {
                TextView content = makeText(context, "› " + line.content, 15 * scale, TEXT);
                content.setBackgroundColor(PANEL_2);
                content.setPadding(dp(context, 14), dp(context, 11), dp(context, 14), dp(context, 11));
                row.addView(content);
            } else {
                TextView content = makeText(context, line.content, 12 * scale, MUTED);
                content.setGravity(Gravity.CENTER);
                content.setPadding(dp(context, 8), dp(context, 4), dp(context, 8), dp(context, 4));
                row.addView(content);
            }
            return row;
        }
    }

    private static TextView makeText(Context c, String text, float sp, int color) {
        TextView t = new TextView(c);
        t.setText(text);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setLineSpacing(0, 1.22f);
        return t;
    }

    private static int dp(Context c, int v) {
        return Math.round(v * c.getResources().getDisplayMetrics().density);
    }
}
