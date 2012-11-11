#!/usr/bin/env python3
# -*- mode: python, coding: utf-8 -*-

import os
import sys
import pty
import signal
from subprocess import Popen, PIPE
from threading import Thread


TERM_INIT = True


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
        self.openterminals = 0
        
        if TERM_INIT:
            print('\033[?1049h')
        Popen(['stty', '-icanon', '-echo', '-isig', '-ixoff', '-ixon'], stdin=sys.stdout).wait()
        
        termsize = (24, 80)
        for channel in (sys.stderr, sys.stdout, sys.stdin):
            termsize = Popen(['stty', 'size'], stdin=channel, stdout=PIPE, stderr=PIPE).communicate()[0]
            if len(termsize) > 0:
                termsize = termsize.decode('utf8', 'replace')[:-1].split(' ') # [:-1] removes a \n
                termsize = [int(item) for item in termsize]
                break
        
        (termh, termw) = termsize
        
        self.curscreen = -1
        self.screens = []
        
        write_thread = WriteThread(self)
        write_thread.daemon = True
        write_thread.start()
        
        midx = termw // 2
        midy = termh // 2
        
        self.screens.append(Screen(1, 1, midx, midy, self))
        self.screens.append(Screen(midx + 1, 1, termw - midx, midy, self))
        self.screens.append(Screen(1, midy + 1, midx, termh - midy, self))
        self.screens.append(Screen(midx + 1, midy + 1, termw - midx, termh - midy, self))
        
        for screen in self.screens:
            screen.daemon = False
            screen.start()
        
        self.curscreen = 0


class WriteThread(Thread):
    def __init__(self, termux):
        Thread.__init__(self)
        self.termux = termux
    
    def run(self):
        try:
            while not sys.stdin.closed:
                b = sys.stdin.read(1)
                if self.termux.curscreen >= 0:
                    self.termux.curscreen &= len(self.termux.screens)
                    self.termux.screens[self.termux.curscreen].writeIn(b);
        except:
            pass


class Screen(Thread):
    def __init__(self, left, top, width, height, termux):
        Thread.__init__(self)
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self.termux = termux
        self.x = 0
        self.y = 0
        self.stored = ''
    
    def run(self):
        self.termux.openterminals += 1
        try:
            (self.master, self.slave) = pty.openpty()
            self.master_write = os.fdopen(self.master, 'wb')
            self.master_read  = os.fdopen(self.master, 'rb', 0)
            self.slave        = os.fdopen(self.slave,  'wb')
            
            read_thread = ReadThread(self.master_read, self.master_write, self)
            read_thread.daemon = True
            read_thread.start()
            
            sttyFlags = ['icanon', 'brkint', 'imaxbel', 'eol', '255', 'eol2', '255', 'swtch', '255', 'ixany', 'iutf8']
            Popen(['stty', 'rows',  str(self.height), 'columns', str(self.width)] + sttyFlags, stdin=self.master_write).wait()
            proc = Popen([os.getenv('SHELL', 'sh')], stdin=self.slave, stdout=self.slave, stderr=self.slave)
            proc.wait()
            
            self.master_write.close()
            self.slave.close()
        finally:
            del self.termux.screens[self.termux.screens.index(self)]
            self.termux.openterminals -= 1
            if self.termux.openterminals == 0:
                Popen(['stty', 'icanon', 'echo', 'isig', 'ixoff', 'ixon'], stdin=sys.stdout).wait()
                if TERM_INIT:
                    print('\033[?1049l')
                os.kill(os.getpid(), signal.SIGTERM)
    
    def writeIn(self, data):
        self.master_write.write(data.encode('utf-8'))
        self.master_write.flush()
    
    
    def writeOut(self, data):
        data = self.stored.encode('utf-8') + data
        self.stored = ''
        
        if (data[-1] & 192) == 128:
            c = 0
            while (data[~c] & 192) == 128:
                c += 1
            if data[~c] >= 128:
                n = 0
                b = data[~c]
                while ((b << n) & 128) == 128:
                    n += 1
                if n > c:
                    self.stored = data[~c:] + self.stored
                    data = data[:~c]
        
        data = data.decode('utf-8', 'replace')
        buf = '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
        i = 0
        n = len(data)
        
        while i < n:
            b = data[i]
            i += 1
            if b == '\n':
                self.y += 1
                self.x = 0
                buf += '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
            elif b == '\033':
                if i == n:
                    self.stored = b + self.stored
                    break
                i -= 1
                b = Util.getcolour(data, i)
                i += len(b)
                if b.startswith('\033['):
                    end = b[-1]
                    if (end == '~') or (('a' <= end) and (end <= 'z')) or (('A' <= end) and (end <= 'Z')):
                        if end == 'H':
                            b = [int(item) for item in b[2 : ~1].split(';')]
                            if len(b) == 2:
                                (self.y, self.x) = b
                                buf += '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
                            else:
                                buf += '\033[' + ';'.join(b) + 'H'
                        else:
                            buf += b
                    else:
                        self.stored = b + self.stored
                        break
                else:
                    buf += b
            else:
                buf += b
                self.x += 1
        
        sys.stdout.buffer.write(buf.encode('utf-8'))


class ReadThread(Thread):
    def __init__(self, reader, writer, screen):
        Thread.__init__(self)
        self.reader = reader
        self.writer = writer
        self.screen = screen
    
    def run(self):
        try:
            while not (self.writer.closed or self.reader.closed):
                b = self.reader.read(1024)
                if b is None:
                    continue
                self.screen.writeOut(b)
                sys.stdout.buffer.flush()
        except:
            pass


'''
Utility set
'''
class Util:
    '''
    Gets colour code att the currect offset in a buffer
    
    @param   input:str   The input buffer
    @param   offset:int  The offset at where to start reading, a escape must begin here
    @return  :str        The escape sequence
    '''
    @staticmethod
    def getcolour(input, offset):
        (i, n) = (offset, len(input))
        rc = input[i]
        i += 1
        if i == n: return rc
        c = input[i]
        i += 1
        rc += c
        
        if c == ']':
            if i == n: return rc
            c = input[i]
            i += 1
            rc += c
            if c == 'P':
                di = 0
                while (di < 7) and (i < n):
                    c = input[i]
                    i += 1
                    di += 1
                    rc += c
            while c == '0':
                c = input[i]
                i += 1
                rc += c
            if c == '4':
                c = input[i]
                i += 1
                rc += c
                if c == ';':
                    c = input[i]
                    i += 1
                    rc += c
                    while c != '\\':
                        c = input[i]
                        i += 1
                        rc += c
        elif c == '[':
            while i < n:
                c = input[i]
                i += 1
                rc += c
                if (c == '~') or (('a' <= c) and (c <= 'z')) or (('A' <= c) and (c <= 'Z')):
                    break
        
        return rc
    
    
    '''
    Calculates the number of visible characters in a text
    
    @param   input:str  The input buffer
    @return  :int       The number of visible characters
    '''
    @staticmethod
    def len(input):
        (rc, i, n) = (0, 0, len(input))
        while i < n:
            c = input[i]
            if c == '\033':
                i += len(Backend.getcolour(input, i))
            else:
                i += 1
                if not UCS.isCombining(c):
                    rc += 1
        return rc


'''
Start if mane script
'''
if __name__ == '__main__':
    Termux()

