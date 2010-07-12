#!/usr/bin/python
#
# Urwid terminal emulation widget unit tests
#    Copyright (C) 2010  aszlig
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public
#    License as published by the Free Software Foundation; either
#    version 2.1 of the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Urwid web site: http://excess.org/urwid/

import os
import sys
import unittest

from itertools import dropwhile

from urwid import vterm
from urwid.main_loop import SelectEventLoop
from urwid import signals

class DummyCommand(object):
    QUITSTRING = '|||quit|||'

    def __init__(self):
        self.reader, self.writer = os.pipe()

    def __call__(self):
        # reset
        sys.stdout.write('\x1bc')

        while True:
            data = os.read(self.reader, 1024)
            if self.QUITSTRING == data:
                break
            sys.stdout.write(data)
            sys.stdout.flush()

    def write(self, data):
        os.write(self.writer, data)

    def quit(self):
        self.write(self.QUITSTRING)

class TermTest(unittest.TestCase):
    def setUp(self):
        self.command = DummyCommand()

        self.term = vterm.TerminalWidget(self.command)
        self.resize(80, 24)

    def tearDown(self):
        self.command.quit()

    def caught_beep(self, obj):
        self.beeped = True

    def resize(self, width, height, soft=False):
        self.termsize = (width, height)
        if not soft:
            self.term.render(self.termsize, focus=False)

    def write(self, data):
        self.command.write(data.replace('\e', '\x1b'))

    def flush(self):
        self.write(chr(0x7f))

    def read(self, raw=False):
        self.term.wait_and_feed()
        rendered = self.term.render(self.termsize, focus=False)
        if raw:
            is_empty = lambda c: c == (None, None, ' ')
            content = list(rendered.content())
            lines = [list(dropwhile(is_empty, reversed(line)))
                     for line in content]
            return [list(reversed(line)) for line in lines if len(line)]
        else:
            content = rendered.text
            lines = [line.rstrip() for line in content]
            return '\n'.join(lines).rstrip()

    def expect(self, what, desc=None, raw=False):
        got = self.read(raw=raw)
        if desc is None:
            desc = ''
        else:
            desc += '\n'
        desc += 'Expected:\n%r\nGot:\n%r' % (what, got)
        self.assertEqual(got, what, desc)

    def test_simplestring(self):
        self.write('hello world')
        self.expect('hello world')

    def test_linefeed(self):
        self.write('hello\x0aworld')
        self.expect('hello\nworld')

    def test_linefeed2(self):
        self.write('aa\b\b\eDbb')
        self.expect('aa\nbb')

    def test_carriage_return(self):
        self.write('hello\x0dworld')
        self.expect('world')

    def test_insertlines(self):
        self.write('\e[0;0flast\e[0;0f\e[10L\e[0;0ffirst\nsecond\n\e[11D')
        self.expect('first\nsecond\n\n\n\n\n\n\n\n\nlast')

    def test_deletelines(self):
        self.write('1\n2\n3\n4\e[2;1f\e[2M')
        self.expect('1\n4')

    def test_movement(self):
        self.write('\e[10;20H11\e[10;0f\e[20C\e[K')
        self.expect('\n' * 9 + ' ' * 19 + '1')
        self.write('\e[A\e[B\e[C\e[D\b\e[K')
        self.expect('')
        self.write('\e[50A2')
        self.expect(' ' * 19 + '2')
        self.write('\b\e[K\e[50B3')
        self.expect('\n' * 23 + ' ' * 19 + '3')
        self.write('\b\e[K' + '\eM' * 30 + '\e[100C4')
        self.expect(' ' * 79 + '4')
        self.write('\e[100D\e[K5')
        self.expect('5')

    def edgewall(self):
        edgewall = '1-\e[1;%(x)df-2\e[%(y)d;1f3-\e[%(y)d;%(x)df-4\x0d'
        self.write(edgewall % {'x': self.termsize[0] - 1,
                               'y': self.termsize[1] - 1})

    def test_horizontal_resize(self):
        self.resize(80, 24)
        self.edgewall()
        self.expect('1-' + ' ' * 76 + '-2' + '\n' * 22
                         + '3-' + ' ' * 76 + '-4')
        self.resize(78, 24, soft=True)
        self.flush()
        self.expect('1-' + '\n' * 22 + '3-')
        self.resize(80, 24, soft=True)
        self.flush()
        self.expect('1-' + '\n' * 22 + '3-')

    def test_vertical_resize(self):
        self.resize(80, 24)
        self.edgewall()
        self.expect('1-' + ' ' * 76 + '-2' + '\n' * 22
                         + '3-' + ' ' * 76 + '-4')
        for y in xrange(23, 1, -1):
            self.resize(80, y, soft=True)
            self.write('\e[%df\e[J3-\e[%d;%df-4' % (y, y, 79))
            desc = "try to rescale to 80x%d." % y
            self.expect('\n' * (y - 2) + '3-' + ' ' * 76 + '-4', desc)
        self.resize(80, 24, soft=True)
        self.flush()
        self.expect('1-' + ' ' * 76 + '-2' + '\n' * 22
                         + '3-' + ' ' * 76 + '-4')

    def write_movements(self, arg):
        fmt = 'XXX\n\e[faaa\e[Bccc\e[Addd\e[Bfff\e[Cbbb\e[A\e[Deee'
        self.write(fmt.replace('\e[', '\e['+arg))

    def test_defargs(self):
        self.write_movements('')
        self.expect('aaa   ddd      eee\n   ccc   fff bbb')

    def test_nullargs(self):
        self.write_movements('0')
        self.expect('aaa   ddd      eee\n   ccc   fff bbb')

    def test_erase_line(self):
        self.write('1234567890\e[5D\e[K\n1234567890\e[5D\e[1K\naaaaaaaaaaaaaaa\e[2Ka')
        self.expect('12345\n      7890\n               a')

    def test_erase_display(self):
        self.write('1234567890\e[5D\e[Ja')
        self.expect('12345a')
        self.write('98765\e[8D\e[1Jx')
        self.expect('   x5a98765')

    def test_scrolling_region_simple(self):
        self.write('\e[10;20r\e[10f1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\e[faa')
        self.expect('aa' + '\n' * 9 + '2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12')

    def test_scrolling_region_reverse(self):
        self.write('\e[2J\e[1;2r\e[5Baaa\r\eM\eM\eMbbb\nXXX')
        self.expect('\n\nbbb\nXXX\n\naaa')

    def test_scrolling_region_move(self):
        self.write('\e[10;20r\e[2J\e[10Bfoo\rbar\rblah\rmooh\r\e[10Aone\r\eM\eMtwo\r\eM\eMthree\r\eM\eMa')
        self.expect('ahree\n\n\n\n\n\n\n\n\n\nmooh')

    def test_scrolling_twice(self):
        self.write('\e[?6h\e[10;20r\e[2;5rtest')
        self.expect('\ntest')

    def test_cursor_scrolling_region(self):
        self.write('\e[?6h\e[10;20r\e[10f1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\e[faa')
        self.expect('\n' * 9 + 'aa\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12')

    def test_relative_region_jump(self):
        self.write('\e[21H---\e[10;20r\e[?6h\e[18Htest')
        self.expect('\n' * 19 + 'test\n---')

    def test_set_multiple_modes(self):
        self.write('\e[?6;5htest')
        self.expect('test')
        self.assertTrue(self.term.term_modes.constrain_scrolling)
        self.assertTrue(self.term.term_modes.reverse_video)
        self.write('\e[?6;5l')
        self.expect('test')
        self.assertFalse(self.term.term_modes.constrain_scrolling)
        self.assertFalse(self.term.term_modes.reverse_video)

    def test_wrap_simple(self):
        self.write('\e[?7h\e[1;%dHtt' % self.term.width)
        self.expect(' ' * (self.term.width - 1) + 't\nt')

    def test_wrap_backspace_tab(self):
        self.write('\e[?7h\e[1;%dHt\b\b\t\ta' % self.term.width)
        self.expect(' ' * (self.term.width - 1) + 'a')

    def test_cursor_visibility(self):
        self.write('\e[?25linvisible')
        self.expect('invisible')
        self.assertEqual(self.term.term.cursor, None)
        self.write('\rvisible\e[?25h\e[K')
        self.expect('visible')
        self.assertNotEqual(self.term.term.cursor, None)

    def test_get_utf8_len(self):
        length = self.term.term.get_utf8_len(chr(int("11110000", 2)))
        self.assertEqual(length, 3)
        length = self.term.term.get_utf8_len(chr(int("11000000", 2)))
        self.assertEqual(length, 1)
        length = self.term.term.get_utf8_len(chr(int("11111101", 2)))
        self.assertEqual(length, 5)

    def test_encoding_unicode(self):
        vterm.util._target_encoding = 'utf-8'
        self.write('\e%G\xe2\x80\x94')
        self.expect('\xe2\x80\x94')

    def test_encoding_unicode(self):
        vterm.util._target_encoding = 'ascii'
        self.write('\e%G\xe2\x80\x94')
        self.expect('?')

    def test_encoding_wrong_unicode(self):
        vterm.util._target_encoding = 'utf-8'
        self.write('\e%G\xc0\x99')
        self.expect('')

    def test_encoding_vt100_graphics(self):
        self.write('\e)0\e(0\x0fg\x0eg\e)Bn\e)0g\e)B\e(B\x0fn')
        self.expect([[
            (None, '0', 'g'), (None, '0', 'g'),
            (None, None, 'n'), (None, '0', 'g'),
            (None, None, 'n')
        ]], raw=True)

    def test_ibmpc_mapping(self):
        self.write('\e[11m\xc4\e[10m\xc4')
        self.expect('q\xc4')
        self.write('\ec\e)U\x0e\xc4\x0f\xc4')
        self.expect('q\xc4')

    def test_set_title(self):
        self._the_title = None

        def _change_title(widget, title):
            self._the_title = title

        signals.connect_signal(self.term, 'title', _change_title)
        self.write('\e]666parsed right?\e\\te\e]0;test title\007st1')
        self.expect('test1')
        self.assertEqual(self._the_title, 'test title')
        self.write('\e]3;stupid title\e\\\e[0G\e[2Ktest2')
        self.expect('test2')
        self.assertEqual(self._the_title, 'stupid title')
        signals.disconnect_signal(self.term, 'title', _change_title)


if __name__ == '__main__':
    unittest.main()
