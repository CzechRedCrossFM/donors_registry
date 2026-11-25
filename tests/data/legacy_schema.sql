CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL, 
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
CREATE TABLE award_eligibility_snapshots (
	medal_id INTEGER NOT NULL, 
	year INTEGER NOT NULL, 
	rodne_cislo VARCHAR(10) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (medal_id, year, rodne_cislo), 
	FOREIGN KEY(medal_id) REFERENCES medals (id)
);
CREATE TABLE awarded_medals (
	rodne_cislo VARCHAR(10) NOT NULL, 
	medal_id INTEGER NOT NULL, 
	awarded_at DATETIME, 
	PRIMARY KEY (rodne_cislo, medal_id), 
	FOREIGN KEY(medal_id) REFERENCES medals (id)
);
CREATE TABLE batches (
	id INTEGER NOT NULL, 
	donation_center_id INTEGER, 
	imported_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(donation_center_id) REFERENCES donation_centers (id)
);
CREATE TABLE contact_import_logs (
	id INTEGER NOT NULL, 
	imported_at DATETIME NOT NULL, 
	imported_by_user_id INTEGER NOT NULL, 
	filename VARCHAR, 
	input_data TEXT NOT NULL, 
	processed_lines_count INTEGER NOT NULL, 
	created_notes_count INTEGER NOT NULL, 
	updated_notes_count INTEGER NOT NULL, 
	emails_added_count INTEGER NOT NULL, 
	phones_added_count INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(imported_by_user_id) REFERENCES users (id)
);
CREATE TABLE donation_centers (
	id INTEGER NOT NULL, 
	slug VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, import_increments BOOLEAN, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);
CREATE TABLE donors_override (
	rodne_cislo CHAR(10) NOT NULL, 
	first_name VARCHAR, 
	last_name VARCHAR, 
	address VARCHAR, 
	city VARCHAR, 
	postal_code CHAR(5), 
	kod_pojistovny CHAR(3), 
	PRIMARY KEY (rodne_cislo)
);
CREATE TABLE donors_overview (
	rodne_cislo VARCHAR(10) NOT NULL, 
	first_name VARCHAR NOT NULL, 
	last_name VARCHAR NOT NULL, 
	address VARCHAR NOT NULL, 
	city VARCHAR NOT NULL, 
	postal_code VARCHAR(5) NOT NULL, 
	kod_pojistovny VARCHAR(3) NOT NULL, 
	donation_count_fm INTEGER NOT NULL, 
	donation_count_fm_bubenik INTEGER NOT NULL, 
	donation_count_trinec INTEGER NOT NULL, 
	donation_count_mp INTEGER NOT NULL, 
	donation_count_total INTEGER NOT NULL, 
	donation_count_manual INTEGER NOT NULL, 
	awarded_medal_br BOOLEAN NOT NULL, 
	awarded_medal_st BOOLEAN NOT NULL, 
	awarded_medal_zl BOOLEAN NOT NULL, 
	awarded_medal_kr3 BOOLEAN NOT NULL, 
	awarded_medal_kr2 BOOLEAN NOT NULL, 
	awarded_medal_kr1 BOOLEAN NOT NULL, 
	awarded_medal_plk BOOLEAN NOT NULL, 
	PRIMARY KEY (rodne_cislo)
);
CREATE TABLE ignored_donors (
	rodne_cislo VARCHAR(10) NOT NULL, 
	reason VARCHAR NOT NULL, 
	ignored_since DATETIME NOT NULL, 
	PRIMARY KEY (rodne_cislo)
);
CREATE TABLE "medals" (
	id INTEGER NOT NULL, 
	slug VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	minimum_donations INTEGER NOT NULL, 
	title_acc VARCHAR NOT NULL, 
	title_instr VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);
CREATE TABLE notes (
	rodne_cislo VARCHAR(10) NOT NULL, 
	note TEXT, 
	PRIMARY KEY (rodne_cislo)
);
CREATE TABLE records (
	id INTEGER NOT NULL, 
	batch_id INTEGER NOT NULL, 
	rodne_cislo VARCHAR(10) NOT NULL, 
	first_name VARCHAR NOT NULL, 
	last_name VARCHAR NOT NULL, 
	address VARCHAR NOT NULL, 
	city VARCHAR NOT NULL, 
	postal_code VARCHAR(5) NOT NULL, 
	kod_pojistovny VARCHAR(3) NOT NULL, 
	donation_count INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(batch_id) REFERENCES batches (id)
);
CREATE TABLE "users" (
	id INTEGER NOT NULL, 
	email VARCHAR(80) NOT NULL, 
	password BLOB NOT NULL, 
	created_at DATETIME NOT NULL, 
	active BOOLEAN, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);
CREATE INDEX ix_awarded_medals_rodne_cislo ON awarded_medals (rodne_cislo);
CREATE INDEX ix_records_rodne_cislo ON records (rodne_cislo);
