#!/usr/bin/env python3
# -*- mode: python, coding: utf-8 -*-

import os
import sys
import pty
import signal
from subprocess import Popen, PIPE
from threading import Thread, Lock


READ_BUF = 4096
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
        
        self.screens.append(Screen(1, 1, termw, termh, self))
        
        #self.screens.append(Screen(1, 1, midx, midy, self))
        #self.screens.append(Screen(midx + 1, 1, termw - midx, midy, self))
        #self.screens.append(Screen(1, midy + 1, midx, termh - midy, self))
        #self.screens.append(Screen(midx + 1, midy + 1, termw - midx, termh - midy, self))
        
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
        self.stored = bytes()
    
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
        data = self.stored + data
        self.stored = bytes()
        
        if (data[-1] & 128) == 128:
            c = 0
            while (data[~c] & 192) == 128:
                c += 1
            if data[~c] >= 128:
                n = 0
                b = data[~c]
                while ((b << n) & 128) == 128:
                    n += 1
                if n - 1 > c:
                    self.stored = data[~c:] + self.stored
                    data = data[:~c]
        
        data = data.decode('utf-8', 'replace').replace(chr(127), chr(8)).replace(chr(8), '\033[D \033[D')
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
                    self.stored = b.encode('utf-8') + self.stored
                    break
                i -= 1
                b = Util.getcolour(data, i)
                i += len(b)
                if b.startswith('\033['):
                    end = b[-1]
                    if (end == '~') or (('a' <= end) and (end <= 'z')) or (('A' <= end) and (end <= 'Z')):
                        if end == 'H':
                            if len(b) == 3:
                                (self.y, self.x) = (0, 0)
                                buf += '\033[%i;%iH' % (self.top, self.left)
                            else:
                                b = [int(item) - 1 for item in b[2 : ~1].split(';')]
                                if len(b) == 2:
                                    (self.y, self.x) = b
                                    buf += '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
                                else:
                                    buf += '\033[' + ';'.join(b) + 'H'
                        elif end == 'A':
                            b = max(1, int('0' + b[2 : ~1].split(';')[-1]))
                            self.y = max(0, self.y - b)
                            buf += '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
                        elif end == 'B':
                            b = max(1, int('0' + b[2 : ~1].split(';')[-1]))
                            self.y += b
                            buf += '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
                        elif end == 'C':
                            b = max(1, int('0' + b[2 : ~1].split(';')[-1]))
                            self.x = min(self.x + b, self.width - 2)
                            buf += '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
                        elif end == 'D':
                            b = max(1, int('0' + b[2 : ~1].split(';')[-1]))
                            self.x = max(0, self.x + b)
                            buf += '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
                        elif end == 'm':
                            buf += b
                        else:
                            buf += b
                    else:
                        self.stored = b.encode('utf-8') + self.stored
                        break
                else:
                    buf += ''.join(['%s ' % d for d in b])
            elif ord(b) == 7:   pass # buf += b # bell
            elif ord(b) == 13:  pass # dismis!
            elif ord(b) < 32:
                pass
            else:
                buf += b
                self.x += 1
                if self.x >= self.width:
                    self.x = 0
                    self.y += 1
                    buf += '\033[%i;%iH' % (self.top + self.y, self.left + self.x)
        
        return buf


readMutex = Lock()
class ReadThread(Thread):
    def __init__(self, reader, writer, screen):
        Thread.__init__(self)
        self.reader = reader
        self.writer = writer
        self.screen = screen
    
    def run(self):
        #try:
            while not (self.writer.closed or self.reader.closed):
                b = self.reader.read(READ_BUF)
                if b is None:
                    continue
                b = self.screen.writeOut(b)
                readMutex.acquire()
                sys.stdout.buffer.write(b.encode('utf-8'))
                sys.stdout.buffer.flush()
                readMutex.release()
        #except:
        #    pass


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
            else:
                while c != ';':
                    c = input[i]
                    i += 1
                    rc += c
                c = rc[2:~1].lstrip('0')
                map = {'0' : '\007', '1' : '\007', '2' : '\007', '4' : '\033\\'}
                if c in map:
                    end = map[c]
                    while not rc.endswith(end):
                        rc += input[i]
                        i += 1
        elif c == '[':
            while i < n:
                c = input[i]
                i += 1
                rc += c
                if (c == '~') or (('a' <= c) and (c <= 'z')) or (('A' <= c) and (c <= 'Z')):
                    break
        
        return rc
    
    
    '''
    Checks whether a character is a combining character
    
    @param   char:chr  The character to test
    @return  :bool     Whether the character is a combining character
    '''
    @staticmethod
    def isCombining(char):
        o = ord(char)
        if (0x0300 <= o) and (o <= 0x036F):  return True
        if (0x20D0 <= o) and (o <= 0x20FF):  return True
        if (0x1DC0 <= o) and (o <= 0x1DFF):  return True
        if (0xFE20 <= o) and (o <= 0xFE2F):  return True
        return False
    
    
    '''
    Gets the number of combining characters in a string
    
    @param   string:str  A text to count combining characters in
    @return  :int        The number of combining characters in the string
    '''
    @staticmethod
    def countCombining(string):
        rc = 0
        for char in string:
            if Util.isCombining(char):
                rc += 1
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
                i += len(Util.getcolour(input, i))
            else:
                i += 1
                if not Util.isCombining(c):
                    rc += 1
        return rc


'''
Start if mane script
'''
if __name__ == '__main__':
    Termux()

