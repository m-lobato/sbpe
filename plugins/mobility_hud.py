'''

+------------------+
|   Mobility HUD   |
|       v0.2       |
|     by Spaze     |
+------------------+

# changelog
- v0.1:  initial "release"
- v0.2:  fixed mini hud scaling; changed selection behavior of hud_type and enabled shells; removed redundant enabled options; changed "space" -> "jump"

'''

# TODO
# additional function for set_color() to call instead of repeating those three lines?
# think about condensing config options (at least the one I'm giving people)

import logging
import util

from _remote import ffi, lib
from manager import PluginBase

MACRON_PLACE_ANIM_IDS = (15, 16, 17)
OFFSET = 1 << 28

ENABLED_OPTS = (
	# 0 show none, 1 show jump, 2 show special, 3 show both
	('wildfire', 3, 'int'),
	('duskwing', 3, 'int'),
	('ironclad', 3, 'int'),
	('fabricator', 3, 'int'),
)

BOX_JUMP_OPTS = (
	('full_color', 0x28ea12, 'color'),
	('half_color', 0xeaa912, 'color'),
	('empty_color', 0xea2412, 'color'),
	('full_opacity', 0.2, 'float'),
	('half_opacity', 0.4, 'float'),
	('empty_opacity', 0.85, 'float'),
	('x', 25, 'int'),  # x position of top left corner
	('y', 300, 'int'),  # y position of top left corner
	('l', 80, 'int'),  # square side length
	('pad', 10, 'int'),  # distance between box edge and description
	('show_num', True, 'bool'),  # show box numbers
	('show_desc', True, 'bool'),  # show box description
)

BOX_SPECIAL_OPTS = (
	('full_color', 0x28ea12, 'color'),
	('half_color', 0xeaa912, 'color'),
	('empty_color', 0xea2412, 'color'),
	('full_opacity', 0.2, 'float'),
	('half_opacity', 0.4, 'float'),
	('empty_opacity', 0.85, 'float'),
	('x', 25, 'int'),  # x position of top left corner
	('y', 405, 'int'),  # y position of top left corner
	('l', 80, 'int'),  # square side length
	('pad', 10, 'int'),  # distance between box edge and description
	('show_num', True, 'bool'),  # show box numbers
	('show_desc', True, 'bool'),  # show box description
)

BOX_MINI_OPTS = (
	('x_offset', 0, 'int'),  # x offset from center of player; I like 48
	('y_offset', 22, 'int'),  # y offset from center of player
	('l', 15, 'int'),  # square side length
	('pad', 5, 'int'),  # distance between boxes
)

TEXT_OPTS = (
	('default_color', 0xffffff, 'color'),
	('outline_color', 0x000000, 'color'),
	('full_opacity', 0.4, 'float'),
	('half_opacity', 0.6, 'float'),
	('empty_opacity', 0.7, 'float'),
	('hud_x', 120, 'int'),
	('hud_y', 200, 'int'),
	('hud_size', 13, 'int'),  # font size for hud text
	('num_size', 40, 'int'),  # font size for box numbers
	('desc_size', 13, 'int'),  # font size for box description
	('outline', 3, 'int'),  # font outline size
	('spacing', 15, 'int'),  # distance between lines of text
)

OPTS = (
	('enabled', ENABLED_OPTS),
	('box_jump', BOX_JUMP_OPTS),
	('box_special', BOX_SPECIAL_OPTS),
	('box_mini', BOX_MINI_OPTS),
	('text', TEXT_OPTS),
)

def addAlpha(color, alpha):
	# from alpha 0 -> 1
	alpha = max(0, min(1, alpha))
	return ((int(alpha * 255) & 0xff) << 24) + (color & 0xffffff)

class Plugin(PluginBase):
	def onInit(self):
		self.config.options('bool', {
			'show_hud': True,
		})
		self.config.options('int', {
			'max_macrons': 2,
			'hud_type': 3,  # 0 show text hud, 1 show just boxes, 2 show just mini, 3 show boxes and mini
		})
		self.config.options('color', {
			'color_white': 0xffffff,
			'color_grey': 0x777777, 
			'color_black': 0x000000,
		})
		self.config.option('text_font', 'HemiHeadBold', 'str')

		for opts in OPTS:
			for opt in opts[1]:
				self.config.option(opts[0] + '_' + opt[0], opt[1], opt[2])
				# logging.info('  ' + opts[0] + '_' + opt[0] + ' = ' + f'{opt[1]}')  # generate config options

		# text
		self.hud_text = util.MultilineText(font=self.config.text_font)
		self.box_jump_num = util.MultilineText()
		self.box_jump_desc = util.MultilineText()
		self.box_special_num = util.MultilineText()
		self.box_special_desc = util.MultilineText()
		self.box_jump_color = self.config.color_grey
		self.box_special_color = self.config.color_grey

		self.last_anim_id = 0
		self.available_macrons = self.config.max_macrons
	
	def afterUpdate(self):
		# update config options
		self.hud_x = self.config.text_hud_x
		self.hud_y = self.config.text_hud_y
		self.hud_text.size = self.config.text_hud_size
		self.hud_text.color = self.config.text_default_color
		self.hud_text.outlineSize = self.config.text_outline
		self.hud_text.outlineColor = self.config.text_outline_color
		self.hud_text.spacing = self.config.text_spacing
		self.box_jump_num.size = self.config.text_num_size
		self.box_special_num.size = self.config.text_num_size
		#! do I need to be updating all of the above?

		self.enabled_jump = False
		self.enabled_special = False

		wc = self.refs.WorldClient
		cw = self.refs.ClientWorld
		# check if player exists
		if wc == ffi.NULL or cw == ffi.NULL:
			self.show_hud = False  # turn off HUD if player doesn't exist
			return
		player = util.clientPlayer(cw)
		if player == ffi.NULL:
			self.show_hud = False  # turn off HUD if player doesn't exist
			return
		ptype = util.getClassName(player)
		if ptype not in self.refs.CASTABLE['PlayerCharacter']:
			return
		nobj = ffi.cast('struct NativeObject *', player)
		wobj = ffi.cast('struct WorldObject *', player)
		pc = ffi.cast('struct PlayerCharacter *', player)

		# set which hud style is active
		if wc.overlay != ffi.NULL:  # don't show hud if menu is open
			self.show_hud = False
		else:
			self.show_hud = self.config.show_hud
		self.hud_type = self.config.hud_type

		# get currently deployed macrons and adjust available macron count
		deployed_macrons = 0
		my_subworld = util.clientMySubWorld(cw)
		if my_subworld == ffi.NULL:
			return
		objects = util.worldobjects(my_subworld.asNativeSubWorld)
		for obj in objects:
			# anything that acts like terrain (macrons)
			if obj.props.terraintype > 0:
				# if placed by player
				if obj.props.ownertype == 1:
					# exit if switching off fab while a macron is deployed (crashes)
					if wobj.props.animprops == ffi.NULL: break
					deployed_macrons += 1
					# check fab animation to see when a new macron is placed
					if (wobj.props.animprops.animid in MACRON_PLACE_ANIM_IDS) and (wobj.props.animprops.animid != self.last_anim_id):
						self.available_macrons -= 1
					self.last_anim_id = wobj.props.animprops.animid

		# determine if on macron or on ground
		onMacron = False
		onGround = False
		if nobj.attached.worldId == 2:
			onMacron = True
		elif nobj.attached.worldId == 1:
			# note: > 0 counts other players' macrons; not sure if all terrain is 1, but it appears so
			onGround = True
		if onGround:
			self.available_macrons = self.config.max_macrons
		
		# set display text per shell
		if util.getClassName(pc) == 'Wildfire':
			num_air_jumps = util.playerField(player, 'numAirJumps')
			max_air_jumps = util.playerField(player, 'maxAirJumps')
			num_air_dashes = util.playerField(player, 'numAirDashes')
			max_air_dashes = util.playerField(player, 'maxAirDashes')
			# text
			self.hud_text.text = f'''
			AirJumps: {num_air_jumps}/{max_air_jumps}
			AirDashes: {num_air_dashes}/{max_air_dashes}'''
			# box
			self.box_jump_num.text = f'{num_air_jumps}/{max_air_jumps}'
			self.box_jump_desc.text = f'Double Jumps'
			self.box_special_num.text = f'{num_air_dashes}/{max_air_dashes}'
			self.box_special_desc.text = f'Blasts'

			self.set_color(num_air_jumps, max_air_jumps, num_air_dashes, max_air_dashes)
			self.set_shown_boxes(self.config.enabled_wildfire)

		elif util.getClassName(pc) == 'Duskwing':
			num_air_jumps = util.playerField(player, 'numAirJumps')
			max_air_jumps = util.playerField(player, 'maxAirJumps')
			num_air_dashes = util.playerField(player, 'numAirDashes')
			max_air_dashes = util.playerField(player, 'maxAirDashes')
			# text
			self.hud_text.text = f'''
			AirJumps: {num_air_jumps}/{max_air_jumps}
			AirDashes: {num_air_dashes}/{max_air_dashes}'''
			# box
			self.box_jump_num.text = f'{num_air_jumps}/{max_air_jumps}'
			self.box_jump_desc.text = f'Double Jumps'
			self.box_special_num.text = f'{num_air_dashes}/{max_air_dashes}'
			self.box_special_desc.text = f'Dashes'

			self.set_color(num_air_jumps, max_air_jumps, num_air_dashes, max_air_dashes)
			self.set_shown_boxes(self.config.enabled_duskwing)

		elif util.getClassName(pc) == 'Ironclad':
			num_air_jumps = util.playerField(player, 'numAirJumps')
			max_air_jumps = util.playerField(player, 'maxAirJumps')
			num_air_mobility = util.playerField(player, 'numAirMobility')
			max_air_mobility = util.playerField(player, 'maxAirMobility')
			# text
			self.hud_text.text = f'''
			AirJumps: {num_air_jumps}/{max_air_jumps}
			AirMobility: {num_air_mobility}/{max_air_mobility}'''
			# crouching: {nobj.crouching}
			# pose: {wobj.props.pose}'''
			# box
			self.box_jump_num.text = f'{num_air_mobility}/{max_air_mobility}'
			self.box_jump_desc.text = f'Boosts'
			self.box_special_num.text = f'{num_air_jumps}/{max_air_jumps}'
			self.box_special_desc.text = f'Double Jumps'

			self.set_color(num_air_mobility, max_air_mobility, num_air_jumps, max_air_jumps)
			self.set_shown_boxes(self.config.enabled_ironclad)

		elif util.getClassName(pc) == 'Fabricator':
			num_air_mobility = util.playerField(player, 'numAirMobility')
			max_air_mobility = util.playerField(player, 'maxAirMobility')
			# text
			self.hud_text.text = f'''
			AirMobility: {num_air_mobility}/{max_air_mobility}
			Macrons: {self.available_macrons}/{self.config.max_macrons}\n
			Deployed Macrons: {deployed_macrons}
			Remaining Macrons: {self.available_macrons}\n'''
			# on Macron: {onMacron}
			# on Ground: {onGround}\n'''
			# attached: {nobj.attached.worldId, nobj.attached.objId}'''
			# box
			self.box_jump_num.text = f'{num_air_mobility}/{max_air_mobility}'
			self.box_jump_desc.text = f'Boosts'
			self.box_special_num.text = f'{self.available_macrons}/{self.config.max_macrons}'
			self.box_special_desc.text = f'Macrons'

			self.set_color(num_air_mobility, max_air_mobility, self.available_macrons, self.config.max_macrons)
			self.set_shown_boxes(self.config.enabled_fabricator)
		
	def onPresent(self):
		if self.show_hud:
			if self.hud_type == 0:  # text
				self.hud_text.draw(self.hud_x, self.hud_y, anchorX=0.5)
			if self.hud_type == 1 or self.hud_type == 3:  # boxes
				if self.enabled_jump:
					self.draw_box('box_jump')
				if self.enabled_special:
					self.draw_box('box_special')
			if self.hud_type == 2 or self.hud_type == 3:  # mini
				if self.enabled_jump:
					self.draw_mini('box_jump')
				if self.enabled_special:
					self.draw_mini('box_special')

	def set_shown_boxes(self, enabled_opt):
		if enabled_opt == 0:
			self.show_hud = False
		elif enabled_opt == 1:
			self.enabled_jump = True
			self.enabled_special = False
		elif enabled_opt == 2:
			self.enabled_jump = False
			self.enabled_special = True
		elif enabled_opt == 3:
			self.enabled_jump = True
			self.enabled_special = True

	def set_color(self, jump_current, jump_max, special_current, special_max):
		# description colors
		self.box_jump_desc.alpha = 0.5
		self.box_jump_desc.color = self.config.text_default_color
		self.box_jump_desc.outlineColor = self.config.text_outline_color
		self.box_special_desc.alpha = 0.5
		self.box_special_desc.color = self.config.text_default_color
		self.box_special_desc.outlineColor = self.config.text_outline_color

		# jump box
		if jump_max == 0:  # zero
			self.box_jump_num.color = self.config.color_grey
			self.box_jump_num.alpha = self.config.text_full_opacity
			self.box_jump_color = addAlpha(self.config.color_grey, self.config.box_jump_full_opacity)
		elif (jump_current % jump_max) == 0 and (jump_current != 0):  # full
			self.box_jump_num.color = self.config.box_jump_full_color
			self.box_jump_num.alpha = self.config.text_full_opacity
			self.box_jump_color = addAlpha(self.config.box_jump_full_color, self.config.box_jump_full_opacity)
		elif jump_current == 0:  # empty
			self.box_jump_num.color = self.config.box_jump_empty_color
			self.box_jump_num.alpha = self.config.text_empty_opacity
			self.box_jump_color =  addAlpha(self.config.box_jump_empty_color, self.config.box_jump_empty_opacity)
		else:  # half
			self.box_jump_num.color = self.config.box_jump_half_color
			self.box_jump_num.alpha = self.config.text_half_opacity
			self.box_jump_color =  addAlpha(self.config.box_jump_half_color, self.config.box_jump_half_opacity)

		# special box
		if special_max == 0:  # zero
			self.box_special_num.color = self.config.color_grey
			self.box_special_num.alpha = self.config.text_full_opacity
			self.box_special_color = addAlpha(self.config.color_grey, self.config.box_special_full_opacity)
		elif (special_current % special_max) == 0 and (special_current != 0):  # full
			self.box_special_num.color = self.config.box_special_full_color
			self.box_special_num.alpha = self.config.text_full_opacity
			self.box_special_color = addAlpha(self.config.box_special_full_color, self.config.box_special_full_opacity)
		elif special_current == 0:  # empty
			self.box_special_num.color = self.config.box_special_empty_color
			self.box_special_num.alpha = self.config.text_empty_opacity
			self.box_special_color =  addAlpha(self.config.box_special_empty_color, self.config.box_special_empty_opacity)
		else:  # half
			self.box_special_num.color = self.config.box_special_half_color
			self.box_special_num.alpha = self.config.text_half_opacity
			self.box_special_color =  addAlpha(self.config.box_special_half_color, self.config.box_special_half_opacity)
		
	def scale(self, value, axis):
		if axis == 'x' or axis == 'X':
			return round(value * self.refs.scaleX)
		elif axis == 'y' or axis == 'Y':
			return round(value * self.refs.scaleY)
		else:
			return value
	
	def draw_box(self, selection=None):
		# `selection` is which box is being drawn, as seen in the OPTS tuple
		if selection == None or (selection != 'box_jump' and selection != 'box_special'):
			return
		
		# set up variables
		x = getattr(self.config, f'{selection}_x')
		y = getattr(self.config, f'{selection}_y')
		l = getattr(self.config, f'{selection}_l')
		pad = getattr(self.config, f'{selection}_pad')
		color = getattr(self, f'{selection}_color')
		num_text = getattr(self, f'{selection}_num')
		desc_text = getattr(self, f'{selection}_desc')
		show_num = getattr(self.config, f'{selection}_show_num')
		show_desc = getattr(self.config, f'{selection}_show_desc')

		# draw box
		self.refs.XDL_FillRect(
			self.scale(x, 'X'), self.scale(y, 'Y'), self.scale(l, 'X'), self.scale(l, 'Y'), color, lib.BLENDMODE_BLEND)
		# draw text
		if show_num:
			num_text.draw(x + (l/2), y + (l/2), anchorX=0.5, anchorY=0.5)
		if show_desc:
			desc_text.draw(x + l + pad, y + (l/2), anchorX=0, anchorY=0.5)
	
	def draw_mini(self, selection=None):
		# `selection` is which box is being drawn, as seen in the OPTS tuple
		if selection == None or (selection != 'box_jump' and selection != 'box_special'):
			return
		wv = self.refs.WorldView
		cw = self.refs.ClientWorld
		if cw == ffi.NULL: return
		player_ptr = util.clientPlayer(cw)
		if player_ptr == ffi.NULL: return
		player = ffi.cast('struct WorldObject *', player_ptr)
		props = player.props

		color = getattr(self, f'{selection}_color')
		bl = self.config.box_mini_l
		if bl <= 0: return

		x = props.xmp // 256 + props.wmp // 512 - wv.offset.x
		y = props.ymp // 256 - wv.offset.y 
		# game space -> window space coords
		x = round(x / self.refs.scaleX)
		y = round(y / self.refs.scaleY)
		bx = x - bl // 2 - self.config.box_mini_x_offset
		by = y - bl - self.config.box_mini_y_offset
		cw = self.refs.canvasW_[0]
		ch = self.refs.canvasH_[0]
		self.refs.canvasW_[0] = self.refs.windowW
		self.refs.canvasH_[0] = self.refs.windowH

		if selection == 'box_jump':
			if self.enabled_special:
				bx = bx - bl // 2 - self.config.box_mini_pad // 2
			self.refs.XDL_FillRect(
				bx, by, bl, bl, color, lib.BLENDMODE_BLEND)
		if selection == 'box_special':
			if self.enabled_jump:
				bx = bx + bl // 2 + self.config.box_mini_pad // 2
			self.refs.XDL_FillRect(
				bx, by, bl, bl, color, lib.BLENDMODE_BLEND)

		# restore coords
		self.refs.canvasW_[0] = cw
		self.refs.canvasH_[0] = ch