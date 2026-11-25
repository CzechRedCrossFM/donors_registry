CREATE TABLE donation_centers (
	id INTEGER NOT NULL IDENTITY,
	slug NVARCHAR(32) NOT NULL,
	title NVARCHAR(max) NOT NULL,
	import_increments BIT NULL DEFAULT 0,
	PRIMARY KEY (id),
	UNIQUE (slug)
)
GO
CREATE TABLE donors_override (
	rodne_cislo NVARCHAR(10) NOT NULL,
	first_name NVARCHAR(max) NULL,
	last_name NVARCHAR(max) NULL,
	address NVARCHAR(max) NULL,
	city NVARCHAR(max) NULL,
	postal_code NVARCHAR(5) NULL,
	kod_pojistovny NVARCHAR(3) NULL,
	PRIMARY KEY (rodne_cislo)
)
GO
CREATE TABLE donors_overview (
	rodne_cislo NVARCHAR(10) NOT NULL,
	first_name NVARCHAR(max) NOT NULL,
	last_name NVARCHAR(max) NOT NULL,
	address NVARCHAR(max) NOT NULL,
	city NVARCHAR(max) NOT NULL,
	postal_code NVARCHAR(5) NOT NULL,
	kod_pojistovny NVARCHAR(3) NOT NULL,
	donation_count_fm INTEGER NOT NULL,
	donation_count_fm_bubenik INTEGER NOT NULL,
	donation_count_trinec INTEGER NOT NULL,
	donation_count_mp INTEGER NOT NULL,
	donation_count_manual INTEGER NOT NULL,
	donation_count_total INTEGER NOT NULL,
	awarded_medal_br BIT NOT NULL,
	awarded_medal_st BIT NOT NULL,
	awarded_medal_zl BIT NOT NULL,
	awarded_medal_kr3 BIT NOT NULL,
	awarded_medal_kr2 BIT NOT NULL,
	awarded_medal_kr1 BIT NOT NULL,
	awarded_medal_plk BIT NOT NULL,
	PRIMARY KEY (rodne_cislo)
)
GO
CREATE TABLE ignored_donors (
	rodne_cislo NVARCHAR(10) NOT NULL,
	reason NVARCHAR(max) NOT NULL,
	ignored_since DATETIME2(6) NOT NULL,
	PRIMARY KEY (rodne_cislo)
)
GO
CREATE TABLE medals (
	id INTEGER NOT NULL IDENTITY,
	slug NVARCHAR(32) NOT NULL,
	title NVARCHAR(max) NOT NULL,
	minimum_donations INTEGER NOT NULL,
	title_acc NVARCHAR(max) NOT NULL,
	title_instr NVARCHAR(max) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (slug)
)
GO
CREATE TABLE notes (
	rodne_cislo NVARCHAR(10) NOT NULL,
	note NVARCHAR(max) NULL,
	PRIMARY KEY (rodne_cislo)
)
GO
CREATE TABLE users (
	id INTEGER NOT NULL IDENTITY,
	email NVARCHAR(80) NOT NULL,
	password VARBINARY(128) NOT NULL,
	created_at DATETIME2(6) NOT NULL,
	active BIT NULL,
	PRIMARY KEY (id),
	UNIQUE (email)
)
GO
CREATE TABLE award_eligibility_snapshots (
	medal_id INTEGER NOT NULL,
	year INTEGER NOT NULL,
	rodne_cislo NVARCHAR(10) NOT NULL,
	created_at DATETIME2(6) NOT NULL,
	PRIMARY KEY (medal_id, year, rodne_cislo),
	FOREIGN KEY(medal_id) REFERENCES medals (id)
)
GO
CREATE TABLE awarded_medals (
	rodne_cislo NVARCHAR(10) NOT NULL,
	medal_id INTEGER NOT NULL,
	awarded_at DATETIME2(6) NULL,
	PRIMARY KEY (rodne_cislo, medal_id),
	FOREIGN KEY(medal_id) REFERENCES medals (id)
)
GO
CREATE INDEX ix_awarded_medals_rodne_cislo ON awarded_medals (rodne_cislo)
GO
CREATE TABLE batches (
	id INTEGER NOT NULL IDENTITY,
	donation_center_id INTEGER NULL,
	imported_at DATETIME2(6) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(donation_center_id) REFERENCES donation_centers (id)
)
GO
CREATE TABLE contact_import_logs (
	id INTEGER NOT NULL IDENTITY,
	imported_at DATETIME2(6) NOT NULL,
	imported_by_user_id INTEGER NOT NULL,
	filename NVARCHAR(max) NULL,
	input_data NVARCHAR(max) NOT NULL,
	processed_lines_count INTEGER NOT NULL,
	created_notes_count INTEGER NOT NULL,
	updated_notes_count INTEGER NOT NULL,
	emails_added_count INTEGER NOT NULL,
	phones_added_count INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(imported_by_user_id) REFERENCES users (id)
)
GO
CREATE TABLE records (
	id INTEGER NOT NULL IDENTITY,
	batch_id INTEGER NOT NULL,
	rodne_cislo NVARCHAR(10) NOT NULL,
	first_name NVARCHAR(max) NOT NULL,
	last_name NVARCHAR(max) NOT NULL,
	address NVARCHAR(max) NOT NULL,
	city NVARCHAR(max) NOT NULL,
	postal_code NVARCHAR(5) NOT NULL,
	kod_pojistovny NVARCHAR(3) NOT NULL,
	donation_count INTEGER NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE CASCADE
)
GO
CREATE INDEX ix_records_rodne_cislo ON records (rodne_cislo)
