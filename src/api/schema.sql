CREATE TABLE IF NOT EXISTS companies (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL DEFAULT '',
 kind TEXT NOT NULL DEFAULT '待识别', procurement TEXT NOT NULL DEFAULT '待核实',
 website TEXT NOT NULL DEFAULT '', social TEXT NOT NULL DEFAULT '', domain TEXT NOT NULL DEFAULT '',
 contact TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL DEFAULT '',
 evidence TEXT NOT NULL DEFAULT '', evidence_url TEXT NOT NULL DEFAULT '',
 source TEXT NOT NULL, checked TEXT NOT NULL, saved INTEGER NOT NULL DEFAULT 0,
 reviewed INTEGER NOT NULL DEFAULT 0, next_action TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 archived_at TEXT, won_at TEXT, won_by TEXT
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

CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 display_name TEXT NOT NULL UNIQUE, role TEXT NOT NULL CHECK(role IN ('admin','sales')),
 password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 must_change INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at INTEGER NOT NULL, remember INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
CREATE TABLE IF NOT EXISTS login_limits (bucket TEXT PRIMARY KEY, hits INTEGER NOT NULL, until INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS alternative_buyers (
 id INTEGER PRIMARY KEY, source_company_id INTEGER NOT NULL REFERENCES companies(id),
 identity TEXT NOT NULL, profile TEXT NOT NULL,
 decision TEXT NOT NULL DEFAULT 'pending' CHECK(decision IN ('pending','adopted','dismissed')),
 company_id INTEGER REFERENCES companies(id),
 proof_url TEXT NOT NULL DEFAULT '', proof_note TEXT NOT NULL DEFAULT '',
 proof_actor TEXT NOT NULL DEFAULT '', proof_at TEXT NOT NULL DEFAULT '',
 UNIQUE(source_company_id,identity)
);
CREATE TABLE IF NOT EXISTS alternative_batches (
 inquiry_id INTEGER PRIMARY KEY REFERENCES inquiries(id), source_company_id INTEGER NOT NULL REFERENCES companies(id),
 generated_at TEXT NOT NULL, mode TEXT NOT NULL, query TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alternative_slots (
 inquiry_id INTEGER NOT NULL REFERENCES alternative_batches(inquiry_id) ON DELETE CASCADE ON UPDATE CASCADE,
 position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 3), candidate_id INTEGER NOT NULL REFERENCES alternative_buyers(id),
 PRIMARY KEY(inquiry_id,position), UNIQUE(inquiry_id,candidate_id)
);

CREATE INDEX IF NOT EXISTS company_name_lookup ON companies(lower(name));
CREATE INDEX IF NOT EXISTS inquiry_company_owner ON inquiries(company_id,owner) WHERE merged_into IS NULL;

CREATE TABLE IF NOT EXISTS outreach_evidence (
 id INTEGER PRIMARY KEY, identity TEXT NOT NULL UNIQUE, source TEXT NOT NULL, edition TEXT NOT NULL,
 title TEXT NOT NULL, market TEXT NOT NULL, url TEXT NOT NULL, snippet TEXT NOT NULL,
 company_id INTEGER REFERENCES companies(id), verdict TEXT NOT NULL DEFAULT '待核实',
 quote TEXT NOT NULL DEFAULT '', author TEXT NOT NULL DEFAULT '', published TEXT NOT NULL DEFAULT '',
 intent TEXT NOT NULL DEFAULT '待判断', fit TEXT NOT NULL DEFAULT 'C', reason TEXT NOT NULL DEFAULT '', reviewer TEXT NOT NULL DEFAULT '',
 updated TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS outreach_company ON outreach_evidence(company_id,verdict,fit);
CREATE TABLE IF NOT EXISTS outreach_contacts (
 id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id), kind TEXT NOT NULL,
 value TEXT NOT NULL, holder TEXT NOT NULL, url TEXT NOT NULL, reviewer TEXT NOT NULL,
 updated TEXT NOT NULL, UNIQUE(company_id,kind,value)
);
CREATE TABLE IF NOT EXISTS outreach_drafts (
 id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id), event TEXT NOT NULL,
 starts TEXT NOT NULL, ends TEXT NOT NULL, booth TEXT NOT NULL, recipient TEXT NOT NULL,
 subject TEXT NOT NULL, body TEXT NOT NULL, actor TEXT NOT NULL, updated TEXT NOT NULL,
 UNIQUE(company_id,event,starts,ends,booth)
);
