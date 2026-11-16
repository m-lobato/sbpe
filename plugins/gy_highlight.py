import logging
import util
import colorsys

from _remote import ffi, lib
from manager import PluginBase

'''
Version: 1.5
Author: Alexrns
Date: 12-4-2022
Source and Config: https://gist.github.com/Alexrns/08ac27bfee1b0db20835ead126426b7b
Description: Highlights engineers (drone makers) and armed pathlights (tiny moving things in boss)
b1.0 --- Highlighting works
b1.1 --- Highlight is now just a white box, cannot change modes with config
b1.2 --- Cleaned up extra code, default is white box, can now change modes with config again
b1.3 --- *Actually* can change modes this time
b1.4 --- No longer exits object search loop when one engineer is off screen, highlight box now accurately reflects
         engineer hitbox with and without border line
b1.4.1 - No longer exits object search loop if one object has no properties (this never happens but better safe)
v1.4.1 - Official release.
v1.5 --- Now can highlight pathlights.
'''

BOX_OPTS = (
	('color', 0xffffff, 'color'),
	# ('color', 0xff0000, 'color'),
	('transparency', 0.6, 'float'),
	('show', True, 'bool'),
)

OUTLINE_OPTS = (
	('color', 0xffffff, 'color'),
	# ('color', 0x00ff00, 'color'),
	('transparency', 1, 'float'),
	('thickness', 2, 'int'),
	('show', False, 'bool'),
)

OPTS = (
	('box', BOX_OPTS),
	('box_outline', OUTLINE_OPTS),
)


class Plugin(PluginBase):
	def onInit(self, inputs=None):
		self.config.option('highlight_engineers', True, 'bool')
		self.config.option('highlight_pathlights', False, 'bool')

		for opts in OPTS:
			for opt in opts[1]:
				self.config.option(opts[0] + '_' + opt[0], opt[1], opt[2])
				# logging.info(f'{opts[0]}_{opt[0]} = {opt[1]}')

		self.config.box_color = (self.config.box_color & 0xffffff) +\
			((int(max(0, min(1, self.config.box_transparency)) * 255) & 0xff) << 24)
		self.config.box_outline_color = (self.config.box_outline_color & 0xffffff) +\
			((int(max(0, min(1, self.config.box_outline_transparency)) * 255) & 0xff) << 24)
		self.config.box_outline_thickness = max(2, self.config.box_outline_thickness)

	def onPresent(self, inputs=None):
		cw = self.refs.ClientWorld
		wv = self.refs.WorldView # might not need check
		if cw == ffi.NULL or wv == ffi.NULL: return

		draw_box = self.config.box_show
		draw_outline = self.config.box_outline_show
		if not draw_box and not draw_outline: return

		# TODO: return when not in gy?

		for obj in util.worldobjects(util.clientServerSubWorld(cw)):
			props = obj.props
			if props == ffi.NULL: continue
			vid = ffi.string(props.vid.s)

			if (vid == b'hulk.scavengerengineer' and self.config.highlight_engineers) or (vid == b'hulk.pathlightarmed' and self.config.highlight_pathlights):
				# if vid == b'lobby.tdummy':
				w = props.wmp // 256
				h = props.hmp // 256
				x = props.xmp // 256 - wv.offset.x
				y = props.ymp // 256 - wv.offset.y
				inbounds = x + w > 0 and y + h > 0 and\
					x < self.refs.canvasW_[0] and\
					y < self.refs.canvasH_[0]

				if not inbounds: continue

				lw = max(2, round(self.config.box_outline_thickness * self.refs.scaleX))
				blnd = lib.BLENDMODE_BLEND

				# draw_outline = True
				# draw_box = True
				if draw_outline:
					if lw * 2 > w or lw * 2 > h:
						self.refs.XDL_FillRect(x, y, w, h, self.config.box_outline_color, blnd)
					else:
						self.refs.XDL_FillRect(x, y, w - lw, lw, self.config.box_outline_color, blnd)
						self.refs.XDL_FillRect(x + lw, y + h - lw, w - lw, lw, self.config.box_outline_color, blnd)
						self.refs.XDL_FillRect(x, y + lw, lw, h - lw, self.config.box_outline_color, blnd)
						self.refs.XDL_FillRect(x + w - lw, y, lw, h - lw, self.config.box_outline_color, blnd)
					x += lw
					y += lw
					w -= lw * 2
					h -= lw * 2
				if draw_box:
					self.refs.XDL_FillRect(x, y, w, h, self.config.box_color, blnd)