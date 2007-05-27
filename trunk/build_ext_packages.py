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

__version__ = "0.4"

import os
import sys
import shutil
import tempfile
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
            os.rename("ext-all.js", "ext-all-debug.js")
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
            print "..Failed to find custom_rhine.jar."
            print "..Make sure that custom_rhino.jar from http://dojotoolkit.org/docs/shrinksafe"
            print "..is in the java CLASSPATH (or just place it in the Ext root directory)."
            sys.exit(1)
    main(args[0], options)
