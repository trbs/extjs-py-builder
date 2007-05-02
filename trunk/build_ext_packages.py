#!/usr/bin/env python

"""This file processes the .jsb files to create working (uncompressed)
files from the SVN file structure that can be used in testing.
Uses ShrinkSafe (http://dojotoolkit.org/docs/shrinksafe) to do minimization
of ext-all.js, which in turn requires Java.

(c) 2007, ActiveState
    Licensed under the MIT License
    
version history:
  0.1: first public version (April 6, 2007)
"""

import os, sys
from cElementTree import ElementTree as ET

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
        filecontents = [open(os.path.join(rootdir, file).replace('\\', '/')).read() for file in files]
        all = '\n'.join(filecontents)
        open(output, 'w').write(all)
    print
    
if len(sys.argv) < 2:
    print "Usage: %s <root_of_ext_svn_dir>" % sys.argv[0]
    sys.exit(0)
    
ext_root = sys.argv[1]
old_cwd = os.getcwd()
try:
    os.chdir(ext_root)
    process_jsb("src/ext.jsb", '.')
    process_jsb("resources/resources.jsb", 'resources')
    os.rename("ext-all.js", "ext-all-debug.js")
    print "Minifying ext-all-debug.js into ext-all.js using ShrinkSafe:",
    sys.stdout.flush()
    retval = os.system("java -jar custom_rhino.jar -c ext-all-debug.js > ext-all.js")

    if retval != 0:
        print "..Couldn't create the compressed ext-all.js"
        print "..Make sure that custom_rhino.jar from http://dojotoolkit.org/docs/shrinksafe"
        print "..is in the java CLASSPATH (or just place it in the Ext root directory)."
    else:
        print "done."
finally:
    os.chdir(old_cwd)
