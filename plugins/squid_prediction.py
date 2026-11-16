import logging
import util
import colorsys

from _remote import ffi, lib
from manager import PluginBase

'''
Version: 3.3
Author: Alexrns
Date: 12-2-2022
Source and Config: https://gist.github.com/Alexrns/c7223c5d5426f19ff8a66697dfbc2079
Description: Shows you where squids will spawn
v2.7.1 - Refactoring
v2.8   - Centered and properly scaled squid box with and without outline
v3.0   - Squid counter is now a real thing and is split into "alive" squids and "total" squids
         No longer pointlessly searches the objects list outside of sc
         No longer returns after one object has no properties (continues instead)
v3.1   - Fixed an issure where a variable was being used as a function and as a boolean
       - Increased spacing between alive counter and total counter by 2
v3.2   - Increased spacing between alive counter and total counter by 6 (now 8)
       - No longer displays counters outside of SC boss, and wipes more variables when leaving boss
v3.3   - Squid counter text position scales properly now
'''

BOX_OPTS = (
    ('default_color', 0xff7f00, 'color'),
	('fade_end_color', 0xff0000, 'color'),
	('fade_start_color', 0xffff00, 'color'),
    ('transparency', 0.6, 'float'),
    ('show', True, 'bool'),
)

OUTLINE_OPTS = (
    ('color', 0xff0000, 'color'),
    ('transparency', 1, 'float'),
    ('thickness', 2, 'int'),
    ('show', True, 'bool'),
)

NUMBER_OPTS = (
    ('size', 16, 'int'),
    ('outline_size', 2, 'int'),
    ('color', 0xffc300, 'color'),
    ('outline_color', 0x000000, 'color'),
    ('show', True, 'bool'),
)

COUNTER_OPTS = (
	('alive_size', 18, 'int'),
	('alive_show', True, 'bool'),
	('total_size', 14, 'int'),
	('total_show', True, 'bool'),
	('x', 400, 'int'),
	('y', 200, 'int'),
)

OPTS = (
	('box', BOX_OPTS),
	('box_outline', OUTLINE_OPTS),
	('number', NUMBER_OPTS),
	('squid_count', COUNTER_OPTS),
)

# a large number that fits in int32 and also unlikely to overflow
OFFSET = 1 << 29


def getRGB(col):
	return ((col >> 16) & 0xff) / 255, ((col >> 8) & 0xff) / 255, (col & 0xff) / 255


def getHex(red, green, blue):
	return ((int(red * 255) & 0xff) << 16) +\
		((int(green * 255) & 0xff) << 8) +\
		(int(blue * 255) & 0xff)


def addAlpha(color, alpha):
	alpha = max(0, min(1, alpha))
	return ((int(alpha * 255) & 0xff) << 24) + (color & 0xffffff)


class Plugin(PluginBase):
	def onInit(self, inputs=None):
		self.config.option('enable', True, 'bool')
		self.config.option('color_fade', True, 'bool')
		self.config.option('hide_green_squids', True, 'bool')
		# self.config.option('', ,)

		for opts in OPTS:
			for opt in opts[1]:
				self.config.option(opts[0] + '_' + opt[0], opt[1], opt[2])
				# logging.info('{0[0]}_{1[0]} = {1[1]}'.format(opts, opt))

		self.alpha = ((int(max(0, min(1, self.config.box_transparency)) * 255) & 0xff) << 24)
		self.config.box_outline_color = addAlpha(self.config.box_outline_color,
			self.config.box_outline_transparency) or OUTLINE_OPTS[0][1]
		self.config.box_outline_thickness = max(2, self.config.box_outline_thickness)

		r, g, b = getRGB(self.config.box_fade_end_color)
		h, s, v = colorsys.rgb_to_hsv(r, g, b)
		self.end_hsv = (h, s, v)
		r, g, b = getRGB(self.config.box_fade_start_color)
		h, s, v = colorsys.rgb_to_hsv(r, g, b)
		self.start_hsv = (h, s, v)
		self.h_diff = self.start_hsv[0] - self.end_hsv[0]

		self.count_down = util.NumberDict(
			size=self.config.number_size, outlineSize=self.config.number_outline_size,
			color=self.config.number_color, outlineColor=self.config.number_outline_color,
		)
		self.alive_text = util.NumberDict(size=self.config.squid_count_alive_size, screenCoords=True)
		self.total_text = util.NumberDict(size=self.config.squid_count_total_size, screenCoords=True)

		self.predict = []
		self.hidden = []
		self.squid_ids = set()

		self.alive_count = 0
		self.total_count = 0

		self.in_boss = False
		self.do_draw = False

	def afterUpdate(self, inputs=None):
		cw = self.refs.ClientWorld
		wv = self.refs.WorldView
		if cw == ffi.NULL or wv == ffi.NULL or not self.config.enable: return

		self.zone = ffi.string(cw.asWorld.props.zone.s) or ffi.string(cw.asWorld.props.music.s)
		if self.zone == b'sc_boss':
			if not self.in_boss:
				self.in_boss = True
		else:
			if self.in_boss:
				self.in_boss = False
				self.total_count = 0
				self.squid_ids = set()
				self.hidden.clear()
				self.predict.clear()
			return

		self.do_draw = True
		self.alive_count = 0
		for obj in util.worldobjects(util.clientServerSubWorld(cw)):
			props = obj.props
			if props == ffi.NULL: continue
			vid = ffi.string(props.vid.s)

			if vid == b'scboss.summons':
				self.alive_count += 1
				if obj.objId not in self.squid_ids:
					self.squid_ids.add(obj.objId)
					self.total_count += 1

			if vid == b'scboss.summonsb':
				if props.move == ffi.NULL: continue
				if props.move.to == ffi.NULL: continue
				move_info = props.move.to

				w = props.wmp
				h = props.hmp
				x = move_info.xmp / 256 - wv.offset.x
				y = move_info.ymp / 256 - wv.offset.y
				inbounds = x > 0 and y > 0 and\
					x < self.refs.canvasW_[0] and\
					y < self.refs.canvasH_[0]

				if inbounds: self.predict.append(obj)
				if self.config.hide_green_squids: self.hide(obj)

	def onPresent(self, inputs=None):
		for obj in self.hidden: obj.props.xmp += OFFSET
		self.hidden.clear()

		if not self.do_draw or not self.in_boss: return

		for obj in self.predict: self.draw(obj)
		self.predict.clear()

		if self.config.squid_count_alive_show:
			self.alive_text.draw(self.alive_count, self.config.squid_count_x, self.config.squid_count_y)
		if self.config.squid_count_total_show:
			self.total_text.draw(self.total_count, self.config.squid_count_x,
				(self.config.squid_count_y + self.config.squid_count_alive_size + 8))

	def draw(self, obj):
		draw_box = self.config.box_show
		draw_outline = self.config.box_outline_show
		draw_timer = self.config.number_show
		if not draw_box and not draw_outline and not draw_timer: return

		p = obj.props
		m = p.move.to

		if m.dt < 0: return

		if m.dt > 500 and self.config.color_fade:
			pos = (1 - m.pos / m.dt)
			h, s, v = self.end_hsv
			new_h = h + pos * self.h_diff
			r, g, b = colorsys.hsv_to_rgb(new_h, s, v)
			box_color = getHex(r, g, b) + self.alpha
		else: box_color = (self.config.box_default_color & 0xffffff) + self.alpha

		wv = self.refs.WorldView
		x, y, w, h = m.xmp // 256 - wv.offset.x, m.ymp // 256 - wv.offset.y, p.wmp // 256, p.hmp // 256
		lw = max(2, round(self.config.box_outline_thickness * self.refs.scaleX))

		if draw_outline:
			if lw * 2 > w or lw * 2 > h:
				self.refs.XDL_FillRect(x, y, w, h, self.config.box_outline_color, lib.BLENDMODE_BLEND)
			else:
				self.refs.XDL_FillRect(x, y, w - lw, lw, self.config.box_outline_color, lib.BLENDMODE_BLEND)
				self.refs.XDL_FillRect(x + lw, y + h - lw,
					w - lw, lw, self.config.box_outline_color, lib.BLENDMODE_BLEND)
				self.refs.XDL_FillRect(x, y + lw, lw, h - lw, self.config.box_outline_color, lib.BLENDMODE_BLEND)
				self.refs.XDL_FillRect(x + w - lw, y,
					lw, h - lw, self.config.box_outline_color, lib.BLENDMODE_BLEND)
			x += lw
			y += lw
			w -= lw * 2
			h -= lw * 2
		if draw_box:
			self.refs.XDL_FillRect(x, y, w, h, box_color, lib.BLENDMODE_BLEND)
		if draw_timer:
			self.count_down.draw(int((m.dt - m.pos) / 10), x + w // 2, y + h // 2, anchorX=0.5, anchorY=0.5)

	def hide(self, obj):
		obj.props.xmp -= OFFSET
		self.hidden.append(obj)