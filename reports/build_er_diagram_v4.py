from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets" / "database-er-schema-v4.png"

W, H = 5200, 3200
BG = "#080B10"
TEXT = "#18202A"
MUTED = "#657180"
GRID = "#CFD5DC"
WHITE = "#F8FAFC"
PHYSICAL = "#55C2FF"
LOGICAL = "#8B98A8"


def font(path, size):
    return ImageFont.truetype(str(path), size)


FONTS = Path("C:/Windows/Fonts")
TITLE = font(FONTS / "msyhbd.ttc", 64)
SUBTITLE = font(FONTS / "msyh.ttc", 28)
TABLE_TITLE = font(FONTS / "consolab.ttf", 31)
COLUMN = font(FONTS / "msyhbd.ttc", 20)
BODY = font(FONTS / "consola.ttf", 22)
BODY_BOLD = font(FONTS / "consolab.ttf", 22)
NOTE = font(FONTS / "msyh.ttc", 23)
NOTE_BOLD = font(FONTS / "msyhbd.ttc", 23)
EDGE = font(FONTS / "msyhbd.ttc", 21)


def f(name, sql_type, key="", constraint=""):
    return (key, name, sql_type, constraint)


tables = {
    "sources": {
        "group": "config",
        "rows": [
            f("source_key", "VARCHAR(64)", "PK"),
            f("module_name", "VARCHAR(64)", "IDX", "NOT NULL"),
            f("label", "VARCHAR(100)", "", "NOT NULL"),
            f("adapter_name", "VARCHAR(255)", "", "NOT NULL"),
            f("resource_type", "VARCHAR(64)", "", "DEFAULT document"),
            f("supported_modes_json", "JSON", "", "NOT NULL"),
            f("enabled", "TINYINT(1)", "", "DEFAULT 1"),
            f("item_limit", "INT UNSIGNED", "", "DEFAULT 10"),
            f("config_json", "JSON", "", "NOT NULL"),
            f("status", "VARCHAR(32)", "", "DEFAULT active"),
            f("created_at", "DATETIME", "", "DEFAULT now"),
            f("updated_at", "DATETIME", "", "AUTO UPDATE"),
        ],
    },
    "monitors": {
        "group": "config",
        "rows": [
            f("id", "BIGINT UNSIGNED", "PK", "AUTO_INCREMENT"),
            f("name", "VARCHAR(255)", "", "NOT NULL"),
            f("module_name", "VARCHAR(64)", "IDX", "NOT NULL"),
            f("query_text", "VARCHAR(255)", "", "NOT NULL"),
            f("aliases_json", "JSON", "", "NOT NULL"),
            f("schedule_type", "ENUM", "", "daily / weekly"),
            f("schedule_time", "TIME", "", "DEFAULT 08:00"),
            f("weekday", "TINYINT UNSIGNED", "", "NULL"),
            f("timezone", "VARCHAR(64)", "", "Asia/Shanghai"),
            f("enabled", "TINYINT(1)", "IDX", "DEFAULT 1"),
            f("last_run_at", "DATETIME", "", "NULL"),
            f("next_run_at", "DATETIME", "IDX", "NULL"),
            f("created_at", "DATETIME", "", "DEFAULT now"),
            f("updated_at", "DATETIME", "", "AUTO UPDATE"),
        ],
    },
    "schema_migrations": {
        "group": "system",
        "rows": [
            f("version", "INT UNSIGNED", "PK"),
            f("name", "VARCHAR(255)", "", "NOT NULL"),
            f("applied_at", "DATETIME", "", "DEFAULT now"),
        ],
    },
    "monitor_sources": {
        "group": "relation",
        "rows": [
            f("monitor_id", "BIGINT UNSIGNED", "PK FK", "-> monitors.id"),
            f("source_key", "VARCHAR(64)", "PK FK", "-> sources.source_key"),
            f("enabled", "TINYINT(1)", "", "DEFAULT 1"),
            f("item_limit", "INT UNSIGNED", "", "DEFAULT 10"),
            f("config_json", "JSON", "", "NOT NULL"),
            f("cursor_json", "JSON", "", "NULL"),
            f("last_success_at", "DATETIME", "", "NULL"),
            f("last_error", "TEXT", "", "NULL"),
            f("updated_at", "DATETIME", "", "AUTO UPDATE"),
        ],
    },
    "monitor_runs": {
        "group": "activity",
        "rows": [
            f("id", "BIGINT UNSIGNED", "PK", "AUTO_INCREMENT"),
            f("monitor_id", "BIGINT UNSIGNED", "FK IDX", "-> monitors.id"),
            f("module_name", "VARCHAR(64)", "IDX", "NOT NULL"),
            f("query_text", "VARCHAR(255)", "", "DEFAULT empty"),
            f("mode", "VARCHAR(16)", "", "DEFAULT search"),
            f("trigger_type", "ENUM", "", "manual / scheduled"),
            f("options_json", "JSON", "", "NOT NULL"),
            f("source_results_json", "JSON", "", "NULL"),
            f("status", "ENUM", "", "5 run states"),
            f("total_fetched", "INT UNSIGNED", "", "DEFAULT 0"),
            f("total_inserted", "INT UNSIGNED", "", "DEFAULT 0"),
            f("total_updated", "INT UNSIGNED", "", "DEFAULT 0"),
            f("error_message", "TEXT", "", "NULL"),
            f("started_at", "DATETIME", "IDX", "DEFAULT now"),
            f("finished_at", "DATETIME", "", "NULL"),
        ],
    },
    "monitor_resource_matches": {
        "group": "relation",
        "rows": [
            f("monitor_id", "BIGINT UNSIGNED", "PK FK", "-> monitors.id"),
            f("module_name", "VARCHAR(64)", "PK", "news / paper / patent"),
            f("resource_uid", "CHAR(36)", "PK", "logical resource link"),
            f("first_run_id", "BIGINT UNSIGNED", "", "logical run link"),
            f("last_run_id", "BIGINT UNSIGNED", "", "logical run link"),
            f("first_matched_at", "DATETIME", "", "DEFAULT now"),
            f("last_matched_at", "DATETIME", "IDX", "DEFAULT now"),
            f("match_count", "INT UNSIGNED", "", "DEFAULT 1"),
            f("relevance_score", "DECIMAL(6,5)", "", "NULL"),
            f("match_reason_json", "JSON", "", "NULL"),
        ],
    },
    "news_resources": {
        "group": "resource",
        "rows": [
            f("id", "BIGINT UNSIGNED", "PK", "AUTO_INCREMENT"),
            f("resource_uid", "CHAR(36)", "UK", "global resource id"),
            f("source_key", "VARCHAR(64)", "UK* IDX", "logical source link"),
            f("resource_type", "VARCHAR(64)", "", "NOT NULL"),
            f("external_id", "VARCHAR(512)", "", "NULL"),
            f("title", "VARCHAR(1000)", "", "NOT NULL"),
            f("url", "TEXT", "", "NOT NULL"),
            f("summary", "MEDIUMTEXT", "", "NULL"),
            f("content", "LONGTEXT", "", "NULL"),
            f("author_display", "VARCHAR(500)", "", "NULL"),
            f("publisher", "VARCHAR(255)", "", "NULL"),
            f("published_at", "DATETIME", "IDX", "NULL"),
            f("language", "VARCHAR(32)", "", "NULL"),
            f("identity_hash", "CHAR(64)", "UK*", "source dedup"),
            f("canonical_hash", "CHAR(64)", "IDX", "cross-source dedup"),
            f("content_hash", "CHAR(64)", "", "change detect"),
            f("metadata_json", "JSON", "", "NULL"),
            f("matched_queries_json", "JSON", "", "NULL"),
            f("first_run_id", "BIGINT UNSIGNED", "", "logical run link"),
            f("last_run_id", "BIGINT UNSIGNED", "", "logical run link"),
            f("first_seen_at", "DATETIME", "", "DEFAULT now"),
            f("last_seen_at", "DATETIME", "IDX", "DEFAULT now"),
        ],
    },
    "paper_resources": {
        "group": "resource",
        "rows": [
            f("id", "BIGINT UNSIGNED", "PK", "AUTO_INCREMENT"),
            f("resource_uid", "CHAR(36)", "UK", "global resource id"),
            f("source_key", "VARCHAR(64)", "UK*", "logical source link"),
            f("resource_type", "VARCHAR(64)", "", "academic_paper"),
            f("external_id", "VARCHAR(512)", "", "NULL"),
            f("journal_key", "VARCHAR(128)", "IDX", "NULL"),
            f("title", "VARCHAR(1000)", "", "NOT NULL"),
            f("url", "TEXT", "", "NOT NULL"),
            f("summary", "MEDIUMTEXT", "", "NULL"),
            f("content", "LONGTEXT", "", "NULL"),
            f("author_display", "VARCHAR(500)", "", "NULL"),
            f("authors_json", "JSON", "", "NULL"),
            f("affiliations_json", "JSON", "", "NULL"),
            f("keywords_json", "JSON", "", "NULL"),
            f("publisher", "VARCHAR(255)", "", "NULL"),
            f("published_at", "DATETIME", "", "NULL"),
            f("publication_date", "VARCHAR(32)", "", "NULL"),
            f("language", "VARCHAR(32)", "", "NULL"),
            f("doi", "VARCHAR(512)", "IDX", "NULL"),
            f("publication_year", "SMALLINT", "IDX", "NULL"),
            f("volume", "VARCHAR(64)", "", "NULL"),
            f("issue", "VARCHAR(64)", "", "NULL"),
            f("pages", "VARCHAR(64)", "", "NULL"),
            f("funding_json", "JSON", "", "NULL"),
            f("citation_text", "TEXT", "", "NULL"),
            f("identity_hash", "CHAR(64)", "UK*", "source dedup"),
            f("canonical_hash", "CHAR(64)", "", "cross-source dedup"),
            f("content_hash", "CHAR(64)", "", "change detect"),
            f("metadata_json", "JSON", "", "NULL"),
            f("matched_queries_json", "JSON", "", "NULL"),
            f("first_run_id", "BIGINT UNSIGNED", "", "logical run link"),
            f("last_run_id", "BIGINT UNSIGNED", "", "logical run link"),
            f("first_seen_at", "DATETIME", "", "DEFAULT now"),
            f("last_seen_at", "DATETIME", "IDX", "DEFAULT now"),
        ],
    },
    "patent_resources": {
        "group": "resource",
        "rows": [
            f("id", "BIGINT UNSIGNED", "PK", "AUTO_INCREMENT"),
            f("resource_uid", "CHAR(36)", "UK", "global resource id"),
            f("source_key", "VARCHAR(64)", "UK*", "logical source link"),
            f("resource_type", "VARCHAR(64)", "", "patent"),
            f("external_id", "VARCHAR(512)", "", "NULL"),
            f("patent_number", "VARCHAR(255)", "IDX", "NULL"),
            f("application_number", "VARCHAR(255)", "", "NULL"),
            f("publication_number", "VARCHAR(255)", "", "NULL"),
            f("title", "VARCHAR(1000)", "", "NOT NULL"),
            f("url", "TEXT", "", "NOT NULL"),
            f("summary", "MEDIUMTEXT", "", "NULL"),
            f("content", "LONGTEXT", "", "NULL"),
            f("applicants_json", "JSON", "", "NULL"),
            f("inventors_json", "JSON", "", "NULL"),
            f("classification_json", "JSON", "", "NULL"),
            f("priority_date", "DATE", "", "NULL"),
            f("application_date", "DATE", "", "NULL"),
            f("publication_date", "DATE", "", "NULL"),
            f("legal_status", "VARCHAR(128)", "", "NULL"),
            f("country_code", "VARCHAR(16)", "", "NULL"),
            f("publisher", "VARCHAR(255)", "", "NULL"),
            f("published_at", "DATETIME", "", "NULL"),
            f("language", "VARCHAR(32)", "", "NULL"),
            f("identity_hash", "CHAR(64)", "UK*", "source dedup"),
            f("canonical_hash", "CHAR(64)", "", "cross-source dedup"),
            f("content_hash", "CHAR(64)", "", "change detect"),
            f("metadata_json", "JSON", "", "NULL"),
            f("matched_queries_json", "JSON", "", "NULL"),
            f("first_run_id", "BIGINT UNSIGNED", "", "logical run link"),
            f("last_run_id", "BIGINT UNSIGNED", "", "logical run link"),
            f("first_seen_at", "DATETIME", "", "DEFAULT now"),
            f("last_seen_at", "DATETIME", "IDX", "DEFAULT now"),
        ],
    },
}


layout = {
    "sources": (80, 300, 1470),
    "monitors": (1780, 300, 1470),
    "schema_migrations": (3660, 300, 1460),
    "monitor_sources": (80, 940, 1470),
    "monitor_runs": (1780, 940, 1470),
    "monitor_resource_matches": (3660, 940, 1460),
    "news_resources": (80, 1750, 1470),
    "paper_resources": (1780, 1750, 1470),
    "patent_resources": (3480, 1750, 1640),
}

HEADER_H = 54
COL_H = 38
ROW_H = 34

group_colors = {
    "config": "#356F9F",
    "relation": "#9A6710",
    "activity": "#586270",
    "resource": "#25796E",
    "system": "#626870",
}


def table_height(name):
    return HEADER_H + COL_H + ROW_H * len(tables[name]["rows"])


def row_y(name, field_name):
    x, y, w = layout[name]
    i = next(i for i, row in enumerate(tables[name]["rows"]) if row[1] == field_name)
    return y + HEADER_H + COL_H + i * ROW_H + ROW_H // 2


def port(name, field_name, side):
    x, y, w = layout[name]
    return (x if side == "left" else x + w, row_y(name, field_name))


image = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(image)


def dashed_line(points, fill=LOGICAL, width=4, dash=18, gap=12):
    for p1, p2 in zip(points, points[1:]):
        x1, y1 = p1
        x2, y2 = p2
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if not length:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        at = 0
        while at < length:
            end = min(at + dash, length)
            draw.line((x1 + ux * at, y1 + uy * at, x1 + ux * end, y1 + uy * end), fill=fill, width=width)
            at += dash + gap


def endpoint(point, color):
    x, y = point
    draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=BG, outline=color, width=4)


def edge(points, label, logical=False, label_at=None):
    if logical:
        dashed_line(points)
        color = LOGICAL
    else:
        draw.line(points, fill=PHYSICAL, width=5, joint="curve")
        color = PHYSICAL
    endpoint(points[0], color)
    endpoint(points[-1], color)
    if label_at:
        x, y = label_at
        box = draw.textbbox((0, 0), label, font=EDGE)
        tw, th = box[2] - box[0], box[3] - box[1]
        draw.rounded_rectangle((x - 12, y - 7, x + tw + 12, y + th + 7), 7, fill=BG, outline=color, width=2)
        draw.text((x, y), label, font=EDGE, fill=color)


# Relationship paths are drawn first, so cards remain completely unobstructed.
edge([port("sources", "source_key", "right"), (1655, row_y("sources", "source_key")), (1655, row_y("monitor_sources", "source_key")), port("monitor_sources", "source_key", "right")], "1 : N", False, (1589, 705))
edge([port("monitors", "id", "left"), (1665, row_y("monitors", "id")), (1665, row_y("monitor_sources", "monitor_id")), port("monitor_sources", "monitor_id", "right")], "1 : N", False, (1589, 840))
edge([port("monitors", "id", "right"), (3370, row_y("monitors", "id")), (3370, row_y("monitor_runs", "monitor_id")), port("monitor_runs", "monitor_id", "right")], "1 : N", False, (3304, 830))
edge([port("monitors", "id", "right"), (3450, row_y("monitors", "id")), (3450, row_y("monitor_resource_matches", "monitor_id")), port("monitor_resource_matches", "monitor_id", "left")], "1 : N", False, (3390, 785))

# Logical source links fan out through the left gutter.
source_start = port("sources", "source_key", "left")
for name, target_x in (("news_resources", 54), ("paper_resources", 1732), ("patent_resources", 3432)):
    target = port(name, "source_key", "left")
    points = [source_start, (38, source_start[1]), (38, 1688), (target_x, 1688), (target_x, target[1]), target]
    edge(points, "", True)

# Run identifiers are deliberately logical links; resource tables stay module-isolated.
run_start = port("monitor_runs", "id", "right")
for name, bus_x in (("news_resources", 1688), ("paper_resources", 3390), ("patent_resources", 5155)):
    target = port(name, "first_run_id", "right")
    edge([run_start, (3405, run_start[1]), (3405, 1655), (bus_x, 1655), (bus_x, target[1]), target], "", True)

# Polymorphic match link: module_name selects one resource table, resource_uid selects the row.
match_start = port("monitor_resource_matches", "resource_uid", "left")
for name, bus_x in (("news_resources", 1618), ("paper_resources", 3318), ("patent_resources", 5100)):
    target = port(name, "resource_uid", "right")
    edge([match_start, (3418, match_start[1]), (3418, 1718), (bus_x, 1718), (bus_x, target[1]), target], "", True)


def draw_table(name):
    x, y, w = layout[name]
    h = table_height(name)
    rows = tables[name]["rows"]
    header = group_colors[tables[name]["group"]]
    draw.rounded_rectangle((x, y, x + w, y + h), radius=8, fill=WHITE, outline="#AAB3BD", width=3)
    draw.rectangle((x, y, x + w, y + HEADER_H), fill=header)
    draw.text((x + 20, y + 9), name, font=TABLE_TITLE, fill="#FFFFFF")
    col_y = y + HEADER_H
    draw.rectangle((x, col_y, x + w, col_y + COL_H), fill="#E8ECF0")
    widths = (100, int(w * 0.32), int(w * 0.29))
    separators = [x + widths[0], x + widths[0] + widths[1], x + widths[0] + widths[1] + widths[2]]
    headings = [("键", x + 15), ("字段", separators[0] + 15), ("类型", separators[1] + 15), ("约束 / 说明", separators[2] + 15)]
    for label, tx in headings:
        draw.text((tx, col_y + 6), label, font=COLUMN, fill="#3C4653")
    for sx in separators:
        draw.line((sx, col_y, sx, y + h), fill=GRID, width=2)
    draw.line((x, col_y + COL_H, x + w, col_y + COL_H), fill="#9FA9B4", width=2)
    for i, (key, field_name, sql_type, constraint) in enumerate(rows):
        ry = col_y + COL_H + i * ROW_H
        if i % 2:
            draw.rectangle((x + 2, ry, x + w - 2, ry + ROW_H), fill="#F1F4F7")
        draw.line((x, ry + ROW_H, x + w, ry + ROW_H), fill=GRID, width=1)
        key_color = "#A33A35" if "PK" in key else ("#1B6B8E" if key else MUTED)
        draw.text((x + 14, ry + 5), key, font=BODY_BOLD if key else BODY, fill=key_color)
        draw.text((separators[0] + 14, ry + 5), field_name, font=BODY_BOLD if "PK" in key else BODY, fill=TEXT)
        draw.text((separators[1] + 14, ry + 5), sql_type, font=BODY, fill=TEXT)
        draw.text((separators[2] + 14, ry + 5), constraint, font=BODY, fill=MUTED)


for table_name in layout:
    draw_table(table_name)

# Title and legend sit above the model and are visually separate from the relationship graph.
draw.text((80, 65), "数据库 ER 图  ·  Schema v4", font=TITLE, fill="#F4F7FA")
draw.text((84, 151), "采集器当前 MySQL 关系模型｜9 张表｜字段、类型、约束完整展开", font=SUBTITLE, fill="#AAB5C2")

legend_x = 3290
draw.line((legend_x, 113, legend_x + 105, 113), fill=PHYSICAL, width=6)
draw.text((legend_x + 126, 94), "实体外键关系", font=NOTE_BOLD, fill="#D8E3ED")
dashed_line([(legend_x + 540, 113), (legend_x + 645, 113)], width=5)
draw.text((legend_x + 666, 94), "逻辑关联", font=NOTE_BOLD, fill="#D8E3ED")
draw.text((legend_x, 150), "逻辑关联不建立跨模块外键，由 source_key、run_id 或 module_name + resource_uid 维护。", font=NOTE, fill="#8996A5")

# Footer key helps a presenter explain the compact index notation.
footer = "PK 主键   FK 外键   UK 唯一键   UK* 联合唯一键的一部分   IDX 普通索引"
draw.text((80, 3135), footer, font=NOTE, fill="#8F9BA9")
draw.text((4170, 3135), "依据：sql/init.sql", font=NOTE, fill="#8F9BA9")

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
image.save(OUTPUT, format="PNG", optimize=True)
print(OUTPUT)
