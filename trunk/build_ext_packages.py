#!/usr/bin/env python

"""This file processes the .jsb files to create working (uncompressed)
files from the SVN file structure that can be used in testing.
Uses ShrinkSafe (http://dojotoolkit.org/docs/shrinksafe) to do minimization
of ext-all.js, which in turn requires Java.

(c) 2007, ActiveState
    Licensed under the MIT License
    
version history:
  0.1: first public version (April 6, 2007)
  0.2: added options and jsmin, fallback on elementtree (April 14, 2007)
  0.3: reduced size by running rhino compressor on source files
  0.4: intermediated release, fixes to much to list here
  0.5: added options again, more error messages
  0.6: added jspacker
  
todo today:
  * restyle entire app
  * add setup.py (and make it a normal unix project)
  * add output path (destination directory for build)
  * add clean option (cleans a build directory)
  * add support for jsdoc (see imported jsdoc source) (check for perl's HTML/Template.pm module)
  * add support for dynamic compression/mimification options
    - 3 methods: jsmin, rhino/dojocompressor, jspacker
    - use OptionParser to dynamicly switch then on and off, also add options to switch between
      at-the-end and on-every-file. like -j -jj -J (respectivly: jsmin, jsmin-every-file, no-jsmin)
    - use profiles:
	- default;  only jsmin the end result. (fasted but less packing)
	- compress; use rhino and jsmin on end result. (slower but smaller sizes)
	- tight;    use rhino and jsmin on every file and end result. (very slow, even smaller size)
	- pack;	    same as compress but also runs jspacker on and result. (very small, but dangeous)

"""

__version__ = "0.6"

import os
import sys
import shutil
import tempfile
import re
from os.path import join as _j
from optparse import OptionParser
try:
    from StringIO import StringIO
except ImportError:
    try:
        from cStringIO import StringIO
    except ImportError:
        print "StringIO not found; u need either StringIO or cStringIO"
try:
    from cElementTree import ElementTree as ET
    cet = True
except ImportError:
    try:
        from elementtree import ElementTree as ET
        cet = False
    except ImportError:
        print "ElementTree not found; u need ElementTree of cElementTree to run this script."
        sys.exit(1)

""" included jsmin, see http://www.crockford.com/javascript/jsmin.py.txt """
def jsmin(js):
    ins = StringIO(js)
    outs = StringIO()
    JavascriptMinify().minify(ins, outs)
    str = outs.getvalue()
    if len(str) > 0 and str[0] == '\n':
        str = str[1:]
    return str

def isAlphanum(c):
    """return true if the character is a letter, digit, underscore,
           dollar sign, or non-ASCII character.
    """
    return ((c >= 'a' and c <= 'z') or (c >= '0' and c <= '9') or
            (c >= 'A' and c <= 'Z') or c == '_' or c == '$' or c == '\\' or (c is not None and ord(c) > 126));

class UnterminatedComment(Exception):
    pass

class UnterminatedStringLiteral(Exception):
    pass

class UnterminatedRegularExpression(Exception):
    pass

class JavascriptMinify(object):

    def _outA(self):
        self.outstream.write(self.theA)
    def _outB(self):
        self.outstream.write(self.theB)

    def _get(self):
        """return the next character from stdin. Watch out for lookahead. If
           the character is a control character, translate it to a space or
           linefeed.
        """
        c = self.theLookahead
        self.theLookahead = None
        if c == None:
            c = self.instream.read(1)
        if c >= ' ' or c == '\n':
            return c
        if c == '': # EOF
            return '\000'
        if c == '\r':
            return '\n'
        return ' '

    def _peek(self):
        self.theLookahead = self._get()
        return self.theLookahead

    def _next(self):
        """get the next character, excluding comments. peek() is used to see
           if a '/' is followed by a '/' or '*'.
        """
        c = self._get()
        if c == '/':
            p = self._peek()
            if p == '/':
                c = self._get()
                while c > '\n':
                    c = self._get()
                return c
            if p == '*':
                c = self._get()
                while 1:
                    c = self._get()
                    if c == '*':
                        if self._peek() == '/':
                            self._get()
                            return ' '
                    if c == '\000':
                        raise UnterminatedComment()

        return c

    def _action(self, action):
        """do something! What you do is determined by the argument:
           1   Output A. Copy B to A. Get the next B.
           2   Copy B to A. Get the next B. (Delete A).
           3   Get the next B. (Delete B).
           action treats a string as a single character. Wow!
           action recognizes a regular expression if it is preceded by ( or , or =.
        """
        if action <= 1:
            self._outA()

        if action <= 2:
            self.theA = self.theB
            if self.theA == "'" or self.theA == '"':
                while 1:
                    self._outA()
                    self.theA = self._get()
                    if self.theA == self.theB:
                        break
                    if self.theA <= '\n':
                        raise UnterminatedStringLiteral()
                    if self.theA == '\\':
                        self._outA()
                        self.theA = self._get()


        if action <= 3:
            self.theB = self._next()
            if self.theB == '/' and (self.theA == '(' or self.theA == ',' or
                                     self.theA == '=' or self.theA == ':' or
                                     self.theA == '[' or self.theA == '?' or
                                     self.theA == '!' or self.theA == '&' or
                                     self.theA == '|'):
                self._outA()
                self._outB()
                while 1:
                    self.theA = self._get()
                    if self.theA == '/':
                        break
                    elif self.theA == '\\':
                        self._outA()
                        self.theA = self._get()
                    elif self.theA <= '\n':
                        raise UnterminatedRegularExpression()
                    self._outA()
                self.theB = self._next()


    def _jsmin(self):
        """Copy the input to the output, deleting the characters which are
           insignificant to JavaScript. Comments will be removed. Tabs will be
           replaced with spaces. Carriage returns will be replaced with linefeeds.
           Most spaces and linefeeds will be removed.
        """
        self.theA = '\n'
        self._action(3)

        while self.theA != '\000':
            if self.theA == ' ':
                if isAlphanum(self.theB):
                    self._action(1)
                else:
                    self._action(2)
            elif self.theA == '\n':
                if self.theB in ['{', '[', '(', '+', '-']:
                    self._action(1)
                elif self.theB == ' ':
                    self._action(3)
                else:
                    if isAlphanum(self.theB):
                        self._action(1)
                    else:
                        self._action(2)
            else:
                if self.theB == ' ':
                    if isAlphanum(self.theA):
                        self._action(1)
                    else:
                        self._action(3)
                elif self.theB == '\n':
                    if self.theA in ['}', ']', ')', '+', '-', '"', '\'']:
                        self._action(1)
                    else:
                        if isAlphanum(self.theA):
                            self._action(1)
                        else:
                            self._action(3)
                else:
                    self._action(1)

    def minify(self, instream, outstream):
        self.instream = instream
        self.outstream = outstream
        self.theA = None
        self.thaB = None
        self.theLookahead = None

        self._jsmin()
        self.instream.close()
""" end of jsmin, see http://www.crockford.com/javascript/jsmin.py.txt """

""" start of jspacker """
##  ParseMaster, version 1.0 (pre-release) (2005/05/12) x6
##  Copyright 2005, Dean Edwards
##  Web: http://dean.edwards.name/
##
##  This software is licensed under the CC-GNU LGPL
##  Web: http://creativecommons.org/licenses/LGPL/2.1/
##
##  Ported to Python by Florian Schulze

import os, re

# a multi-pattern parser

class Pattern:
    def __init__(self, expression, replacement, length):
        self.expression = expression
        self.replacement = replacement
        self.length = length

    def __str__(self):
        return "(" + self.expression + ")"

class Patterns(list):
    def __str__(self):
        return '|'.join([str(e) for e in self])

class ParseMaster:
    # constants
    EXPRESSION = 0
    REPLACEMENT = 1
    LENGTH = 2
    GROUPS = re.compile(r"""\(""", re.M)#g
    SUB_REPLACE = re.compile(r"""\$\d""", re.M)
    INDEXED = re.compile(r"""^\$\d+$""", re.M)
    TRIM = re.compile(r"""(['"])\1\+(.*)\+\1\1$""", re.M)
    ESCAPE = re.compile(r"""\\.""", re.M)#g
    #QUOTE = re.compile(r"""'""", re.M)
    DELETED = re.compile("""\x01[^\x01]*\x01""", re.M)#g

    def __init__(self):
        # private
        self._patterns = Patterns()   # patterns stored by index
        self._escaped = []
        self.ignoreCase = False
        self.escapeChar = None

    def DELETE(self, match, offset):
        return "\x01" + match.group(offset) + "\x01"

    def _repl(self, a, o, r, i):
        while (i):
            m = a.group(o+i-1)
            if m is None:
                s = ""
            else:
                s = m
            r = r.replace("$" + str(i), s)
            i = i - 1
        r = ParseMaster.TRIM.sub("$1", r)
        return r

    # public
    def add(self, expression="^$", replacement=None):
        if replacement is None:
            replacement = self.DELETE
        # count the number of sub-expressions
        #  - add one because each pattern is itself a sub-expression
        length = len(ParseMaster.GROUPS.findall(self._internalEscape(str(expression)))) + 1
        # does the pattern deal with sub-expressions?
        if (isinstance(replacement, str) and ParseMaster.SUB_REPLACE.match(replacement)):
            # a simple lookup? (e.g. "$2")
            if (ParseMaster.INDEXED.match(replacement)):
                # store the index (used for fast retrieval of matched strings)
                replacement = int(replacement[1:]) - 1
            else: # a complicated lookup (e.g. "Hello $2 $1")
                # build a function to do the lookup
                i = length
                r = replacement
                replacement = lambda a,o: self._repl(a,o,r,i)
        # pass the modified arguments
        self._patterns.append(Pattern(expression, replacement, length))

    # execute the global replacement
    def execute(self, string):
        if self.ignoreCase:
            r = re.compile(str(self._patterns), re.I | re.M)
        else:
            r = re.compile(str(self._patterns), re.M)
        string = self._escape(string, self.escapeChar)
        string = r.sub(self._replacement, string)
        string = self._unescape(string, self.escapeChar)
        string = ParseMaster.DELETED.sub("", string)
        return string

    # clear the patterns collections so that this object may be re-used
    def reset(self):
        self._patterns = Patterns()

    # this is the global replace function (it's quite complicated)
    def _replacement(self, match):
        i = 1
        # loop through the patterns
        for pattern in self._patterns:
            if match.group(i) is not None:
                replacement = pattern.replacement
                if callable(replacement):
                    return replacement(match, i)
                elif isinstance(replacement, (int, long)):
                    return match.group(replacement+i)
                else:
                    return replacement
            else:
                i = i+pattern.length

    # encode escaped characters
    def _escape(self, string, escapeChar=None):
        def repl(match):
            char = match.group(1)
            self._escaped.append(char)
            return escapeChar
        if escapeChar is None:
            return string
        r = re.compile("\\"+escapeChar+"(.)", re.M)
        result = r.sub(repl, string)
        return result

    # decode escaped characters
    def _unescape(self, string, escapeChar=None):
        def repl(match):
            try:
                #result = eval("'"+escapeChar + self._escaped.pop(0)+"'")
                result = escapeChar + self._escaped.pop(0)
                return result
            except IndexError:
                return escapeChar
        if escapeChar is None:
            return string
        r = re.compile("\\"+escapeChar, re.M)
        result = r.sub(repl, string)
        return result

    def _internalEscape(self, string):
        return ParseMaster.ESCAPE.sub("", string)


##   packer, version 2.0 (2005/04/20)
##   Copyright 2004-2005, Dean Edwards
##   License: http://creativecommons.org/licenses/LGPL/2.1/

##  Ported to Python by Florian Schulze

## http://dean.edwards.name/packer/

class JavaScriptPacker:
    def __init__(self):
        self._basicCompressionParseMaster = self.getCompressionParseMaster(False)
        self._specialCompressionParseMaster = self.getCompressionParseMaster(True)

    def basicCompression(self, script):
        return self._basicCompressionParseMaster.execute(script)

    def specialCompression(self, script):
        return self._specialCompressionParseMaster.execute(script)

    def getCompressionParseMaster(self, specialChars):
        IGNORE = "$1"
        parser = ParseMaster()
        parser.escapeChar = '\\'
        # protect strings
        parser.add(r"""'[^']*?'""", IGNORE)
        parser.add(r'"[^"]*?"', IGNORE)
        # remove comments
        parser.add(r"""//[^\n\r]*?[\n\r]""")
        parser.add(r"""/\*[^*]*?\*+([^/][^*]*?\*+)*?/""")
        # protect regular expressions
        parser.add(r"""\s+(\/[^\/\n\r\*][^\/\n\r]*\/g?i?)""", "$2")
        parser.add(r"""[^\w\$\/'"*)\?:]\/[^\/\n\r\*][^\/\n\r]*\/g?i?""", IGNORE)
        # remove: ;;; doSomething();
        if specialChars:
            parser.add(""";;;[^\n\r]+[\n\r]""")
        # remove redundant semi-colons
        parser.add(r""";+\s*([};])""", "$2")
        # remove white-space
        parser.add(r"""(\b|\$)\s+(\b|\$)""", "$2 $3")
        parser.add(r"""([+\-])\s+([+\-])""", "$2 $3")
        parser.add(r"""\s+""", "")
        return parser

    def getEncoder(self, ascii):
        mapping = {}
        base = ord('0')
        mapping.update(dict([(i, chr(i+base)) for i in range(10)]))
        base = ord('a')
        mapping.update(dict([(i+10, chr(i+base)) for i in range(26)]))
        base = ord('A')
        mapping.update(dict([(i+36, chr(i+base)) for i in range(26)]))
        base = 161
        mapping.update(dict([(i+62, chr(i+base)) for i in range(95)]))

        # zero encoding
        # characters: 0123456789
        def encode10(charCode):
            return str(charCode)

        # inherent base36 support
        # characters: 0123456789abcdefghijklmnopqrstuvwxyz
        def encode36(charCode):
            l = []
            remainder = charCode
            while 1:
                result, remainder = divmod(remainder, 36)
                l.append(mapping[remainder])
                if not result:
                    break
                remainder = result
            l.reverse()
            return "".join(l)

        # hitch a ride on base36 and add the upper case alpha characters
        # characters: 0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
        def encode62(charCode):
            l = []
            remainder = charCode
            while 1:
                result, remainder = divmod(remainder, 62)
                l.append(mapping[remainder])
                if not result:
                    break
                remainder = result
            l.reverse()
            return "".join(l)

        # use high-ascii values
        def encode95(charCode):
            l = []
            remainder = charCode
            while 1:
                result, remainder = divmod(remainder, 95)
                l.append(mapping[remainder+62])
                if not result:
                    break
                remainder = result
            l.reverse()
            return "".join(l)

        if ascii <= 10:
            return encode10
        elif ascii <= 36:
            return encode36
        elif ascii <= 62:
            return encode62
        return encode95

    def escape(self, script):
        script = script.replace("\\","\\\\")
        script = script.replace("'","\\'")
        script = script.replace('\n','\\n')
        #return re.sub(r"""([\\'](?!\n))""", "\\$1", script)
        return script

    def escape95(self, script):
        result = []
        for x in script:
            if x>'\xa1':
                x = "\\x%0x" % ord(x)
            result.append(x)
        return "".join(result)

    def encodeKeywords(self, script, encoding, fastDecode):
        # escape high-ascii values already in the script (i.e. in strings)
        if (encoding > 62):
            script = self.escape95(script)
        # create the parser
        parser = ParseMaster()
        encode = self.getEncoder(encoding)
        # for high-ascii, don't encode single character low-ascii
        if encoding > 62:
            regexp = r"""\w\w+"""
        else:
            regexp = r"""\w+"""
        # build the word list
        keywords = self.analyze(script, regexp, encode)
        encoded = keywords['encoded']
        # encode
        def repl(match, offset):
            return encoded.get(match.group(offset), "")
        parser.add(regexp, repl)
        # if encoded, wrap the script in a decoding function
        script = parser.execute(script)
        script = self.bootStrap(script, keywords, encoding, fastDecode)
        return script

    def analyze(self, script, regexp, encode):
        # analyse
        # retreive all words in the script
        regexp = re.compile(regexp, re.M)
        all = regexp.findall(script)
        sorted = [] # list of words sorted by frequency
        encoded = {} # dictionary of word->encoding
        protected = {} # instances of "protected" words
        if all:
            unsorted = []
            _protected = {}
            values = {}
            count = {}
            all.reverse()
            for word in all:
                word = "$"+word
                if word not in count:
                    count[word] = 0
                    j = len(unsorted)
                    unsorted.append(word)
                    # make a dictionary of all of the protected words in this script
                    #  these are words that might be mistaken for encoding
                    values[j] = encode(j)
                    _protected["$"+values[j]] = j
                count[word] = count[word] + 1
            # prepare to sort the word list, first we must protect
            #  words that are also used as codes. we assign them a code
            #  equivalent to the word itself.
            # e.g. if "do" falls within our encoding range
            #      then we store keywords["do"] = "do";
            # this avoids problems when decoding
            sorted = [None] * len(unsorted)
            for word in unsorted:
                if word in _protected and isinstance(_protected[word], int):
                    sorted[_protected[word]] = word[1:]
                    protected[_protected[word]] = True
                    count[word] = 0
            unsorted.sort(lambda a,b: count[b]-count[a])
            j = 0
            for i in range(len(sorted)):
                if sorted[i] is None:
                    sorted[i]  = unsorted[j][1:]
                    j = j + 1
                encoded[sorted[i]] = values[i]
        return {'sorted': sorted, 'encoded': encoded, 'protected': protected}

    def encodePrivate(self, charCode):
        return "_"+str(charCode)

    def encodeSpecialChars(self, script):
        parser = ParseMaster()
        # replace: $name -> n, $$name -> $$na
        def repl(match, offset):
            #print offset, match.groups()
            length = len(match.group(offset + 2))
            start = length - max(length - len(match.group(offset + 3)), 0)
            return match.group(offset + 1)[start:start+length] + match.group(offset + 4)
        parser.add(r"""((\$+)([a-zA-Z\$_]+))(\d*)""", repl)
        # replace: _name -> _0, double-underscore (__name) is ignored
        regexp = r"""\b_[A-Za-z\d]\w*"""
        # build the word list
        keywords = self.analyze(script, regexp, self.encodePrivate)
        # quick ref
        encoded = keywords['encoded']
        def repl(match, offset):
            return encoded.get(match.group(offset), "")
        parser.add(regexp, repl)
        return parser.execute(script)

    # build the boot function used for loading and decoding
    def bootStrap(self, packed, keywords, encoding, fastDecode):
        ENCODE = re.compile(r"""\$encode\(\$count\)""")
        # $packed: the packed script
        #packed = self.escape(packed)
        #packed = [packed[x*10000:(x+1)*10000] for x in range((len(packed)/10000)+1)]
        #packed = "'" + "'+\n'".join(packed) + "'\n"
        packed = "'" + self.escape(packed) + "'"

        # $count: number of words contained in the script
        count = len(keywords['sorted'])

        # $ascii: base for encoding
        ascii = min(count, encoding) or 1

        # $keywords: list of words contained in the script
        for i in keywords['protected']:
            keywords['sorted'][i] = ""
        # convert from a string to an array
        keywords = "'" + "|".join(keywords['sorted']) + "'.split('|')"

        encoding_functions = {
            10: """ function($charCode) {
                        return $charCode;
                    }""",
            36: """ function($charCode) {
                        return $charCode.toString(36);
                    }""",
            62: """ function($charCode) {
                        return ($charCode < _encoding ? "" : arguments.callee(parseInt($charCode / _encoding))) +
                            (($charCode = $charCode % _encoding) > 35 ? String.fromCharCode($charCode + 29) : $charCode.toString(36));
                    }""",
            95: """ function($charCode) {
                        return ($charCode < _encoding ? "" : arguments.callee($charCode / _encoding)) +
                            String.fromCharCode($charCode % _encoding + 161);
                    }"""
        }

        # $encode: encoding function (used for decoding the script)
        encode = encoding_functions[encoding]
        encode = encode.replace('_encoding',"$ascii")
        encode = encode.replace('arguments.callee', "$encode")
        if ascii > 10:
            inline = "$count.toString($ascii)"
        else:
            inline = "$count"
        # $decode: code snippet to speed up decoding
        if fastDecode:
            # create the decoder
            decode = r"""// does the browser support String.replace where the
                        //  replacement value is a function?
                        if (!''.replace(/^/, String)) {
                            // decode all the values we need
                            while ($count--) $decode[$encode($count)] = $keywords[$count] || $encode($count);
                            // global replacement function
                            $keywords = [function($encoded){return $decode[$encoded]}];
                            // generic match
                            $encode = function(){return'\\w+'};
                            // reset the loop counter -  we are now doing a global replace
                            $count = 1;
                        }"""
            if encoding > 62:
                decode = decode.replace('\\\\w', "[\\xa1-\\xff]")
            else:
                # perform the encoding inline for lower ascii values
                if ascii < 36:
                    decode = ENCODE.sub(inline, decode)
            # special case: when $count==0 there ar no keywords. i want to keep
            #  the basic shape of the unpacking funcion so i'll frig the code...
            if not count:
                raise NotImplemented
                #) $decode = $decode.replace(/(\$count)\s*=\s*1/, "$1=0");


        # boot function
        unpack = r"""function($packed, $ascii, $count, $keywords, $encode, $decode) {
                        while ($count--)
                            if ($keywords[$count])
                                $packed = $packed.replace(new RegExp("\\b" + $encode($count) + "\\b", "g"), $keywords[$count]);
                        return $packed;
                    }"""
        if fastDecode:
            # insert the decoder
            #unpack = re.sub(r"""\{""", "{" + decode + ";", unpack)
            unpack = unpack.replace('{', "{" + decode + ";", 1)

        if encoding > 62: # high-ascii
            # get rid of the word-boundaries for regexp matches
            unpack = re.sub(r"""'\\\\b'\s*\+|\+\s*'\\\\b'""", "", unpack)
        if ascii > 36 or encoding > 62 or fastDecode:
            # insert the encode function
            #unpack = re.sub(r"""\{""", "{$encode=" + encode + ";", unpack)
            unpack = unpack.replace('{', "{$encode=" + encode + ";", 1)
        else:
            # perform the encoding inline
            unpack = ENCODE.sub(inline, unpack)
        # pack the boot function too
        unpack = self.pack(unpack, 0, False, True)

        # arguments
        params = [packed, str(ascii), str(count), keywords]
        if fastDecode:
            # insert placeholders for the decoder
            params.extend(['0', "{}"])

        # the whole thing
        return "eval(" + unpack + "(" + ",".join(params) + "))\n";

    def pack(self, script, encoding=0, fastDecode=False, specialChars=False, compaction=True):
        script = script+"\n"
        self._encoding = encoding
        self._fastDecode = fastDecode
        if specialChars:
            script = self.specialCompression(script)
            script = self.encodeSpecialChars(script)
        else:
            if compaction:
                script = self.basicCompression(script)
        if encoding:
            script = self.encodeKeywords(script, encoding, fastDecode)
        return script
""" end of jspacker """

def process_jsb(fname, output_dir):
    print "Processing", fname
    rootdir = os.path.dirname(fname)
    jsb = ET(file=fname)
    root = jsb.getroot()
    for package in root.findall("target"):
        output = os.path.normpath(package.attrib['file'].replace('$output', output_dir).replace('\\', '/'))
        print "..creating", output
        dirname = os.path.dirname(output)
        if dirname and not os.path.exists(dirname): os.makedirs(dirname)
        files = [file.attrib['name'] for file in package.findall("include")]
        p = lambda file: _j(rootdir, file).replace('\\', '/')
        if options.no_continue:
            all = '\n'.join(open(p(file)).read() for file in files)
        else:
            all = '\n'.join(open(p(file)).read() for file in files if os.path.isfile(p(file)))
        open(output, 'w').write(all)
    print

def main(ext_root, options):
    if not os.path.isfile(_j(ext_root, "src", "ext.jsb")):
        print "Target directory is not a ExtJS svn checkout directory"
        sys.exit(1)
    old_cwd = os.getcwd()
    try:
        try:
            os.chdir(ext_root)
            process_jsb("src/ext.jsb", '.')
            process_jsb("resources/resources.jsb", 'resources')
	    shutil.copy("ext-all.js", "ext-all-debug.js")
            if options.shrinksafe:
                print "Minifying ext-all.js using ShrinkSafe:",
                sys.stdout.flush()
                retval = os.system("java -jar custom_rhino.jar -opt -1 -c ext-all-debug.js > ext-all.js")
                if retval != 0:
                    print "..Couldn't create the compressed ext-all.js"
                    print "..Make sure that custom_rhino.jar from http://dojotoolkit.org/docs/shrinksafe"
                    print "..is in the java CLASSPATH (or just place it in the Ext root directory)."
                    shutil.copy("ext-all-debug.js", "ext-all.js")
                else:
                    print "done."
            if options.jsmin:
                print "Minifying ext-all.js using jsmin:",
                sys.stdout.flush()
                try:
                    f = open("ext-all.js")
                    data = f.read()
                    f.close()
                    f = open("ext-all.js", "wb")
                    f.write(jsmin(data))
                    f.close()
                except Exception, e:
                    print "error in jsmin:", e
                    open("ext-all.js", "wb").write(data)
                else:
                    print "done."
            if options.jspacker:
                print "Minifying ext-all.js using jspacker:",
                sys.stdout.flush()
                try:
                    p = JavaScriptPacker()
                    f = open("ext-all.js")
                    data = f.read()
                    f.close()
                    f = open("ext-all.js", "wb")
                    f.write(p.pack(data, compaction=False, encoding=62, fastDecode=True))
                    f.close()
                except Exception, e:
                    print "error in jspacker:", e
                    open("ext-all.js", "wb").write(data)
                else:
                    print "done."                
        except Exception, e:
            print "Buiding Failed"
            raise e
        else:
            print "Buiding Completed"
    finally:
        os.chdir(old_cwd)

def found_on_classpath(jar):
    for path in os.environ.get("CLASSPATH", "").split(";"):
        if path and jar in os.listdir(os.path.abspath(path)):
            return True
    return False

if __name__=="__main__":
    usage = "%prog [options] <root_of_ext_svn_dir>"
    parser = OptionParser(usage=usage, version=__version__)
    parser.add_option("-s", "--shrinksafe", action="store_true", dest="shrinksafe",
    					default=True, help="Use shrinksafe for packing ext-all.js")
    parser.add_option("-S", "--no-shrinksafe", action="store_false", dest="shrinksafe",
    					help="Disable shrinksafe")
    #parser.add_option("-o", "--shrinksafe-opt", action="store", type="string", dest="shrinkopt",
    #					default=-1, help="ShrinkSafe optimalization level")
    parser.add_option("-j", "--jsmin", action="store_true", dest="jsmin",
    					default=True, help="Use jsmin to minifie ext-all.js")
    parser.add_option("-J", "--no-jsmin", action="store_false", dest="jsmin",
    					help="Disable jsmin")
    parser.add_option("-p", "--jspacker", action="store_true", dest="jspacker",
    					default=False, help="Use jspacker to minifie ext-all.js")
    parser.add_option("-P", "--no-jspacker", action="store_false", dest="jspacker",
    					help="Disable jspacker")
    parser.add_option("-C", "--no-continue", action="store_true", dest="no_continue",
    					default=False, help="Do not continue building if file(s) do not exist.")
    parser.add_option("-f", "--force", action="store_true", dest="force",
       					default=False, help="Force build, keep running even if options fail.")
    
    global options
    (options, args) = parser.parse_args()
    if len(args)!=1:
        parser.print_help()
        sys.exit(0)
    if options.shrinksafe:
        rhino = "custom_rhino.jar"
        if not os.path.isfile(rhino) or not found_on_classpath(rhino):
	    if options.no_continue:
        	print "..Failed to find custom_rhine.jar."
    		print "..Make sure that custom_rhino.jar from http://dojotoolkit.org/docs/shrinksafe"
    		print "..is in the java CLASSPATH (or just place it in the Ext root directory)."
    	        sys.exit(1)
	    else:
        	print "Failed to find custom_rhine.jar. Disabling ShrinkSafe"
		options.shrinksafe = False
		
    main(args[0], options)
