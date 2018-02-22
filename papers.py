#!/usr/bin/env python3

import argparse
import os
import sqlite3
import shutil
import re
from datetime import datetime
from collections import namedtuple

class Color(object):
	FAIL = '\033[91m'
	STATUS_READ = '\033[38;5;198m'
	STATUS_WIP = '\033[38;5;195m'
	STATUS_SKIMMED = '\033[38;5;210m'
	STATUS_UNREAD = '\033[38;5;219m'
	MATCHING = '\033[38;5;120m'
	_ENDC = '\033[0m'
	
	@staticmethod
	def wrap(s,c):
		""" Wrap s with color c and the terminator """
		return "{}{}{}".format(c, s, Color._ENDC)
	
	@staticmethod
	def fail(s):
		return Color.wrap(s, Color.FAIL)
	
	@staticmethod
	def matching(s):
		return Color.wrap(s, Color.MATCHING)
	
	# This respects the case of the occurrence inside the string
	@staticmethod
	def highlight_matches(s, match):
		""" Highlight all the occurrences of match in s with the MATCHING color """
		pattern = re.compile(match, re.IGNORECASE)
		for m in re.finditer(pattern, s):
			s = s[0:m.start()] + Color.matching(s[m.start():m.end()]) + s[m.end():]
		return s

class Status(object):
	STATUS_TO_CODE = {
		'unread'  : 0,
		'wip'	  : 1,
		'skimmed' : 2,
		'read'	  : 3
	}
	CODE_TO_STATUS = { v:k for k,v in STATUS_TO_CODE.items() }

	@staticmethod
	def max_length():
		return max(map(lambda x : len(x), Status.STATUS_TO_CODE.keys()))

	def __init__(self, string_or_code):
		super(Status, self).__init__()
		if type(string_or_code) == str:
			self.string = string_or_code
			assert(self.string in Status.STATUS_TO_CODE.keys()), \
				Color.fail("Invalid string for status")
			self.code = Status.STATUS_TO_CODE[self.string]
		elif type(string_or_code) == int:
			self.code = string_or_code
			assert(self.code in Status.CODE_TO_STATUS.keys()), \
				Color.fail("Invalid string for status")
			self.string = Status.CODE_TO_STATUS[self.code]
		else:
			assert(0), Color.fail("Status requires either a string or an int")

	@property
	def color(self):
		return {
			'unread' : Color.STATUS_UNREAD,
			'wip'    : Color.STATUS_WIP,
			'skimmed': Color.STATUS_SKIMMED,
			'read'   : Color.STATUS_READ,			
		}[self.string]

class Database(object):
	SCHEMA = '''
		CREATE TABLE papers (
			id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
			title TEXT NOT NULL,
			relpath TEXT NOT NULL UNIQUE,
			date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
			status INTEGER DEFAULT 0
		);
		
		CREATE TABLE keywords (
			pid INTEGER REFERENCES papers(id) ON UPDATE CASCADE,
			word TEXT
		);
	
		-- FUTURE: authors management
		CREATE TABLE authors (
			pid INTEGER REFERENCES papers(id) ON UPDATE CASCADE,
			name TEXT
		);
	
		-- FUTURE: associations between papers
		CREATE TABLE links (
			pid1 INTEGER REFERENCES papers(id),
			pid2 INTEGER REFERENCES papers(id)
		);
	'''

	# Tuple representing the DB entries for the table "papers"
	Entry = namedtuple('Entry', 'id title relpath date_added status')

	def __init__(self, db_path, setup=False):
		super(Database, self).__init__()
		self.path = db_path
		if setup:
			# should not exist if we're setting up
			assert(not os.path.exists(self.path)), \
				Color.fail('Database already exists during setup procedure')
		self.conn = sqlite3.connect(self.path)
		self.cur = self.conn.cursor()
		if setup:
			# create schema
			self.cur.executescript(Database.SCHEMA)

	def translate_last(method):
		"""
		Convert 'last' to the pid of the last added paper.
		Decorator to be applied to every method that takes a paper id (as a last argument)
		"""
		def wrapped(instance, *args):
			# always pass pid as the last argument
			pid_arg = args[-1]
			arg_list = list(args)
			arg_list[-1] = instance.last_paper()[0] if pid_arg == 'last' else pid_arg
			return method(instance, *tuple(arg_list))
		return wrapped

	# Print error generated from sqlite3
	def _err(self, desc, e):
		print("{}: {}".format(desc, Color.fail(e.args[0])))

	# returns an Entry
	def last_paper(self):
		""" Retrieve the last added paper """
		try:
			self.cur.execute('''
				SELECT * FROM papers
				ORDER BY date_added DESC
			''')
			return Database.Entry(*self.cur.fetchone())
		except sqlite3.Error as e:
			self._err("Error retrieving last paper", e)

	@translate_last
	def add_keyword(self, word, pid):
		try:
			self.cur.execute('''
				INSERT INTO keywords(pid, word)
				VALUES (?,?)
			''', (pid, word.strip()))
			self.conn.commit()
		except sqlite3.Error as e:
			self._err("Error adding keyword", e)

	@translate_last
	def remove_keyword(self, word, pid):
		try:
			self.cur.execute('''
				DELETE FROM keywords
				WHERE pid = ? AND word = ?
			''', (pid, word))
			self.conn.commit()
		except sqlite3.Error as e:
			self._err("Error removing keyword", e)

	# returns a list of Entity
	@translate_last
	def get_keywords(self, pid):
		""" Retrieve all the keywords associated to a certain paper """
		try:
			self.cur.execute('''
				SELECT word FROM keywords 
				WHERE pid = ?
			''', (pid,))
			return list(map(lambda x : x[0], self.cur.fetchall()))
		except sqlite3.Error as e:
			self._err("Error retrieving keywords", e)

	def insert(self, title, relpath, keywords):
		""" Insert a paper entry into the database (and possibly the keywords) """
		try:
			self.cur.execute('''
				INSERT INTO papers(title, relpath) 
				VALUES(?,?)''', 
				(title, relpath))
			pid = self.last_paper().id
			for kword in keywords:
				self.add_keyword(kword, pid)
			self.conn.commit()
		except sqlite3.Error as e:
			self._err("Error inserting paper", e)

	# returns an Entry
	@translate_last
	def find_paper(self, pid):
		try:
			self.cur.execute("SELECT * FROM papers WHERE id = ?", (pid,))
			return Database.Entry(*self.cur.fetchone())
		except sqlite3.Error as e:
			self._err("Error retrieving paper", e)

	@translate_last
	def remove(self, pid):
		""" Remove a paper from the DB """
		try:
			found = self.find_paper(pid)
			relpath = found.relpath
			self.cur.execute("DELETE FROM papers WHERE id = ?", (pid,))
			self.conn.commit()
			return relpath
		except sqlite3.Error as e:
			self._err("Error deleting paper", e)

	def search(self, title=None, keyword=None):
		"""
		Search the papers, expose an iterator.
		Note that if both title and keyword are None, all the papers will match.
		(This is indeed how Papers.list() is implemented)
		"""
		try:
			self.cur.execute('''
				SELECT * FROM papers
				ORDER BY date_added DESC
			''')
			# Construct entries
			entries = map(lambda x : Database.Entry(*x), self.cur.fetchall())
			# Everything will match is nothing has been specified
			match_all = (title is None and keyword is None)
			for entry in entries:
				# default to True is the respective param is None
				title_match = (title is None)
				keyword_match = (keyword is None)
				stored_keywords = self.get_keywords(entry.id)
				if keyword is not None:
					low_keyword = keyword.lower()
					keyword_match = any(map(lambda x : x.lower().find(low_keyword) != -1,  stored_keywords))
				if title is not None:
					title_match = title.lower() in entry.title.lower()
				if match_all or (keyword_match or title_match):
					yield entry, stored_keywords
		except sqlite3.Error as e:
			self._err("Error retrieving paper list", e)

	@translate_last
	def update_status(self, status, pid):
		""" Update the reading status of a paper """
		try:
			code = Status(status).code
			self.cur.execute('''
				UPDATE papers
				SET status = ?
				WHERE id = ?
			''', (code, pid))
			self.conn.commit()
		except sqlite3.Error as e:
			self._err("Error updating paper status", e)

	def close(self):
		self.conn.commit()
		self.conn.close()


class Storage(object):
	def __init__(self, storage_dir, setup=False):
		super(Storage, self).__init__()
		self.directory = storage_dir
		if setup:
			# setting up, create dir
			assert(not os.path.exists(self.directory)), \
				Color.fail('Storage directory already exists during setup procedure')
			os.makedirs(self.directory)

	def paper_subdir(self, ntitle):
		""" Subdirectory of a paper given the normalized title """
		return os.path.join(self.directory, ntitle)

	def add(self, file, title):
		""" Import a paper (create subdir, copy file, create notes.txt) """
		normalized_title = title.replace(' ','_').lower()
		paper_dir = self.paper_subdir(normalized_title)
		assert(not os.path.exists(paper_dir)), \
			Color.fail('{} already exists'.format(paper_dir))
		os.makedirs(paper_dir)
		shutil.copy2(file, paper_dir)
		open(os.path.join(paper_dir, 'notes.txt'), 'a').close()
		return os.path.relpath(paper_dir, self.directory)

	def delete(self, relpath):
		full_path = os.path.join(self.directory, relpath)
		assert(os.path.isdir(full_path)), Color.fail('{} does not exist'.format(full_path))
		shutil.rmtree(full_path)

class Papers(object):
	ENV_VAR = 'PAPERS_DIR'
	STORAGE_DIR_NAME = 'storage'
	DB_NAME = 'papers.db'

	def __init__(self, setup=False):
		super(Papers, self).__init__()
		env = os.getenv(Papers.ENV_VAR)
		assert(env is not None), \
			Color.fail('Could not get environment variable {}. Did you export it?'.format(Config.ENV_VAR))
		self.base_dir = os.path.abspath(os.getenv(Papers.ENV_VAR))
		if setup:
			assert(not os.path.exists(self.base_dir)), \
				Color.fail('Base directory already exists during setup procedure')
		self.storage_path = self.subpath(Papers.STORAGE_DIR_NAME)
		self.db_path = self.subpath(Papers.DB_NAME)
		self.storage = Storage(self.storage_path, setup=setup)
		self.db = Database(self.db_path, setup=setup)

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.db.close()

	def subpath(self,p):
		return os.path.join(self.base_dir, p)
		
	def add(self, file, title, keywords):
		""" Add a paper """
		assert(os.path.exists(file)), Color.fail('{} does not exist'.format(file))
		# Get relpath from the storage
		relpath = self.storage.add(file, title)
		# use it to insert the paper in the DB
		self.db.insert(title, relpath, keywords)

	def delete(self, pid):
		""" Delete a paper """
		# get relpath from the db
		relpath = self.db.remove(pid)
		# use it to delete it from the storage
		self.storage.delete(relpath)

	# only return the Entry objects
	def list(self):
		""" List all the papers """
		result = []
		for entry, keywords in self.db.search(title=None, keyword=None):
			result.append(entry)
		return result

	# iterator yielding both entry and keywords
	def filter(self, title=None, keyword=None):
		""" Filter the papers based on title and keyword """
		assert(title is not None or keyword is not None), \
			Color.fail("Either title or keyword should not be empty")
		return self.db.search(title=title, keyword=keyword)

	def last(self):
		return self.db.last_paper()

	def mark(self, status, pid):
		""" Update reading status """
		self.db.update_status(status, pid)

	# specify whether we want the keywords or not
	def retrieve(self, pid, keywords=False):
		""" Retrieve a paper with the given pid """
		entry = self.db.find_paper(pid)
		assert(entry is not None), Color.fail("Could not retrieve paper")
		if keywords:
			stored_keywords = self.db.get_keywords(pid)
			return (entry, stored_keywords)
		return (entry,)

	def tag(self, keyword, pid):
		""" Associate keyword to a paper """
		self.db.add_keyword(keyword, pid)

	def untag(self, keyword, pid):
		""" Remove keyword from a paper """
		self.db.remove_keyword(keyword, pid)

	# only works on macOS, I guess
	def open(self, pid):
		""" Open the subfolder for a given paper """
		entry = self.db.find_paper(pid)
		full_path = self.storage.paper_subdir(entry.relpath)
		os.system('open ' + full_path)
'''
-------------------------------------------------------------
-------------------------------------------------------------
-------------------------------------------------------------
'''

# need to declare it here because of the @subcommand decorator
parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter)
parser.epilog = """

Initial setup:
  $ export {}=~/path/to/papers/dir
  $ papers init

Import a paper (and create notes.txt inside the import folder):
  $ papers import -f reflections.pdf -t 'Reflections on Trusting Trust'

List all the papers (along with date and their reading status):
  $ papers list -s -d

Associate a certain keyword to the last added paper:
  $ papers word -a security -p last

Search and display the papers with a certain keyword associated to them:
  $ papers search -k security

""".format(Papers.ENV_VAR)
subparsers = parser.add_subparsers(description=None, dest="subcommand")
subparsers.required = True

# Credit: https://gist.github.com/mivade/384c2c41c3a29c637cb6c603d4197f9f
def arg(*name_or_flags, **kwargs):
	return ([*name_or_flags], kwargs)

# decorator for sub commands
def subcommand(args=[], parent=subparsers):
	def decorator(func):
		name = func.__name__.replace('cmd_','')
		parser = parent.add_parser(name, help=func.__doc__)
		for arg in args:
			parser.add_argument(*arg[0], **arg[1])
		parser.set_defaults(func=func)
	return decorator


@subcommand()
def cmd_init(args):
	"""Initialize the papers directory (first use only)."""
	with Papers(setup=True) as p:
		print("Initialized {} as Papers directory".format(p.base_dir))


@subcommand([
	arg('-f','--file', required=True, help="The file you want to import."),
	arg('-t','--title', required=True, help="The title of the paper being imported."),
	arg('-k','--keywords', help='Comma-separated list of keywords')
])
def cmd_import(args):
	"""Import a new paper."""
	keywords = []
	if args.keywords is not None:
		keywords = args.keywords.split(',')
	with Papers() as p:
		p.add(args.file, args.title, keywords=keywords)
		print("Imported '{}'".format(args.title))


@subcommand([
	arg('-p','--paper_id', required=True, help="The identifier of the paper to delete.")
])
def cmd_delete(args):
	"""Delete a paper and all the data related to it."""
	with Papers() as p:
		p.delete(args.paper_id)
		print("Removed {}".format(args.paper_id))

# returns a formatted representation of a paper
# (on a single line) 
def format_entry(p, status=False, date=False):
	sp = " " * 4
	elements = []
	# justify to maintain alignment
	pid = str(p.id).rjust(4)
	elements.append(pid)
	if date:
		# include the date, formatted as "Month Day, Year"
		date_obj = datetime.strptime(p.date_added, '%Y-%m-%d %H:%M:%S').date()
		date_str = date_obj.strftime('%b %d, %Y')
		elements.append(date_str)
	if status:
		# include the status, colored
		status = Status(p.status)
		elements.append(Color.wrap(status.string.rjust(Status.max_length()), status.color))
	elements.append(p.title)
	return sp.join(elements)


@subcommand([
	arg('-s', '--show-status', required=False, 
		action='store_true', help="Show status of each paper."),
	arg('-d', '--show-date', required=False, 
		action='store_true', help="Show date of each paper.")
])
def cmd_list(args):
	"""List papers."""
	with Papers() as p:
		for paper in p.list():
			print(format_entry(paper, status=args.show_status, date=args.show_date))


@subcommand([
	arg('-s', '--show-status', required=False, 
		action='store_true', help="Show status of the paper."),
	arg('-d', '--show-date', required=False, 
		action='store_true', help="Show date of the paper.")
])
def cmd_last(args):
	"""Retrieve the last added paper."""
	with Papers() as p:
		print(format_entry(p.last(), status=args.show_status, date=args.show_date))


@subcommand([
	arg('-s', '--status', required=True, choices=[ 'unread', 'wip', 'skimmed', 'read' ], 
		help="Read status of the paper."),
	arg('-p','--paper_id', required=True, help="The identifier of the paper to update.")
])
def cmd_mark(args):
	"""Set the status of a paper."""
	with Papers() as p:
		p.mark(args.status, args.paper_id)
		print("Marked {} as {}".format(args.paper_id, args.status))


# multiline formatting of certain paper information
def format_title_keywords(title, keywords):
	s  = "   Title: '{}'\n".format(title)
	s += "Keywords: {}".format(', '.join(keywords))
	return s


@subcommand([
	arg('-a','--add', help='Associate a keyword to a paper.'),
	arg('-r','--remove', help='Remove a keyword from a paper.'),
	arg('-l','--list', action='store_true', help='List all the keywords associated to a paper.'),
	arg('-p','--paper_id', required=True, help="The identifier of the paper to update.")
])
def cmd_word(args):
	"""Manage keywords associated with a paper."""
	def check_opts(x):
		assert(x), Color.fail("Only one action can be specified")

	with Papers() as p:
		if args.list:
			check_opts(args.add is None and args.remove is None)
			entry, keywords = p.retrieve(args.paper_id, keywords=True)
			print(format_title_keywords(entry.title, keywords))
		elif args.add is not None:
			check_opts(args.remove is None)
			p.tag(args.add, args.paper_id)
		elif args.remove is not None:
			p.untag(args.remove, args.paper_id)


@subcommand([
	arg('-k', '--keyword', help='Search on keywords.'),
	arg('-t', '--title', help='Search on paper titles')
])
def cmd_search(args):
	"""Search through keywords and titles"""
	with Papers() as p:
		for paper, keywords in p.filter(args.title, args.keyword):
			title = paper.title
			if args.keyword is not None:
				keywords = map(lambda x : Color.highlight_matches(x, args.keyword), keywords)
			if args.title is not None:
				title = Color.highlight_matches(title, args.title)
			print(format_title_keywords(title, keywords) + '\n')


@subcommand([
	arg('-p','--paper_id', required=True, help="The identifier of the paper to open.")
])
def cmd_open(args):
	"""Open the directory containing the given paper."""
	with Papers() as p:
		p.open(args.paper_id)


if __name__ == '__main__':
	args = parser.parse_args()
	args.func(args)