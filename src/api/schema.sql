CREATE TABLE IF NOT EXISTS companies (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL DEFAULT '',
 kind TEXT NOT NULL DEFAULT '待识别', procurement TEXT NOT NULL DEFAULT '待核实',
 website TEXT NOT NULL DEFAULT '', social TEXT NOT NULL DEFAULT '', domain TEXT NOT NULL DEFAULT '',
 contact TEXT NOT NULL DEFAULT '',
 evidence TEXT NOT NULL DEFAULT '', evidence_url TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL, checked TEXT NOT NULL, saved INTEGER NOT NULL DEFAULT 0,
 reviewed INTEGER NOT NULL DEFAULT 0, next_action TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS company_domain ON companies(domain) WHERE domain <> '';
CREATE TABLE IF NOT EXISTS inquiries (
 id INTEGER PRIMARY KEY, company_id INTEGER REFERENCES companies(id), buyer TEXT NOT NULL,
 owner TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '待处理', intent TEXT NOT NULL,
 next_action TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, last_in TEXT NOT NULL, replied TEXT,
 merged_into INTEGER REFERENCES inquiries(id)
);
CREATE TABLE IF NOT EXISTS threads (
 channel TEXT NOT NULL, account TEXT NOT NULL, thread_key TEXT NOT NULL,
 inquiry_id INTEGER NOT NULL REFERENCES inquiries(id), PRIMARY KEY(channel,account,thread_key)
);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, inquiry_id INTEGER NOT NULL REFERENCES inquiries(id),
 channel TEXT NOT NULL, account TEXT NOT NULL, event_id TEXT NOT NULL, thread_key TEXT NOT NULL,
 sender TEXT NOT NULL, body TEXT NOT NULL, at TEXT NOT NULL, origin TEXT NOT NULL,
 features TEXT NOT NULL DEFAULT '{}', attachment TEXT NOT NULL DEFAULT '', answered INTEGER NOT NULL DEFAULT 0,
 UNIQUE(channel,account,event_id)
);
CREATE TABLE IF NOT EXISTS history (
 id INTEGER PRIMARY KEY, inquiry_id INTEGER NOT NULL REFERENCES inquiries(id),
 at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cursors (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS channel_sync (
 provider TEXT PRIMARY KEY, last_attempt TEXT NOT NULL, last_success TEXT, error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS messages_inquiry ON messages(inquiry_id,at);
CREATE INDEX IF NOT EXISTS inquiries_last ON inquiries(last_in);
