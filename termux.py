#!/usr/bin/env python3
# -*- mode: python, coding: utf-8 -*-

import os
import sys
import pty
import signal
from subprocess import Popen, PIPE
from threading import Thread


TERM_INIT = False


'''
Hack to enforce UTF-8 in output (in the future, if you see anypony not using utf-8 in
programs by default, report them to Princess Celestia so she can banish them to the moon)

@param  text:str  The text to print (empty string is default)
@param  end:str   The appendix to the text to print (line breaking is default)
'''
def print(text = '', end = '\n'):
    sys.stdout.buffer.write((str(text) + end).encode('utf-8'))
    sys.stdout.buffer.flush()

'''
stderr equivalent to print()

@param  text:str  The text to print (empty string is default)
@param  end:str   The appendix to the text to print (line breaking is default)
'''
def printerr(text = '', end = '\n'):
    sys.stderr.buffer.write((str(text) + end).encode('utf-8'))
    sys.stderr.buffer.flush()



class Termux:
    def __init__(self):
        if TERM_INIT:
            print('\033[?1049h')
        try:
            Popen(['stty', '-icanon', '-echo', '-isig', '-ixoff', '-ixon'], stdin=sys.stdout).wait()
            
            (master, slave) = pty.openpty()
            master_write = os.fdopen(master, 'wb')
            master_read  = os.fdopen(master, 'rb', 0)
            slave        = os.fdopen(slave,  'wb')
            
            termsize = (24, 80)
            for channel in (sys.stderr, sys.stdout, sys.stdin):
                termsize = Popen(['stty', 'size'], stdin=channel, stdout=PIPE, stderr=PIPE).communicate()[0]
                if len(termsize) > 0:
                    termsize = termsize.decode('utf8', 'replace')[:-1].split(' ') # [:-1] removes a \n
                    termsize = [int(item) for item in termsize]
                    break
            
            write_thread = WriteThread(master_read, master_write)
            read_thread = ReadThread(master_read, master_write)
            for thread in (write_thread, read_thread):
                thread.daemon = True
                thread.start()
            
            Popen(['stty', 'rows', str(termsize[0]), 'columns', str(termsize[1]), '-icanon', 'brkint', 'imaxbel', 'eol', '255', 'eol2', '255', 'swtch', '255', 'ixany', 'iutf8'], stdin=master_write).wait()
            proc = Popen([os.getenv('SHELL', 'sh')], stdin=slave, stdout=slave, stderr=slave)
            proc.wait()
            
            master_write.close()
            slave.close()
        finally:
            Popen(['stty', 'icanon', 'echo', 'isig', 'ixoff', 'ixon'], stdin=sys.stdout).wait()
            if TERM_INIT:
                print('\033[?1049l')
            os.kill(os.getpid(), signal.SIGTERM)


class WriteThread(Thread):
    def __init__(self, reader, writer):
        Thread.__init__(self)
        self.reader = reader
        self.writer = writer
    
    def run(self):
        try:
            while not (sys.stdin.closed or self.writer.closed or self.reader.closed):
                b = sys.stdin.read(1)
                self.writer.write(b.encode('utf-8'))
                self.writer.flush()
        except:
            pass


class ReadThread(Thread):
    def __init__(self, reader, writer):
        Thread.__init__(self)
        self.reader = reader
        self.writer = writer
    
    def run(self):
        try:
            while not (self.writer.closed or self.reader.closed):
                b = self.reader.read(1024)
                sys.stdout.buffer.write(b)
                sys.stdout.buffer.flush()
        except:
            pass


if __name__ == '__main__':
    Termux()

