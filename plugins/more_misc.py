"""
Version: 1.11.0
Author: Alexrns
Date: 12-2-2022
Source and Config: https://gist.github.com/Alexrns/25d5a143bf91427dea6ca3ffc3132746
Description:
#################################################### Features ####################################################
+--Custom Background--+--Additional Noise Hiding--+----------------------Auto Config----------------------+
| Custom BG color     | Hides fake vq mid bullets | Automatically sets variable values upon entering zone |
| BG color can fade   | Can hide aura (!A)        | Works with any plugin variable                        |
+---------------------+---------------------------+-------------------------------------------------------+
+----------------------------Additional HUD------------------------------+
| Mini values (small text above shell):                                  |
| .   hp                                                                 |
| .   ammo                                                               |
| .   ammo spam timer (lobby / home)                                     |
| DW spin bar (duration must be changed in the config for now sadly)     |
| EC Counter:                                                            |
| .   Shows amount of ec gained in last zone and current play session    |
| Server Reminder:                                                       |
| .   Shows which server you are in below the EC Counter in the top left |
+------------------------------------------------------------------------+
+-------------------------------SC Close Time-------------------------------+
| Displays time sc will close upon opening (must be in game for first port) |
| Also prints close time to console                                         |
| Plays sound when first port opens (!N)                                    |
| Plays sound when all deposits are filled just before opening (!N)         |
+---------------------------------------------------------------------------+
+------------------------------------Auto Config Rules------------------------------------+
| format: PLUGIN OPTION ZONE = VALUE                                                      |
| zones:                                                                                  |
| .   shop = secret shop                                                                  |
| .   home = where you keep your stuff                                                    |
| .   lobby = Eschaton Station                                                            |
| .   ice, iceHard, ice_boss = (Elite) Frozen Blight                                      |
| .   forest, forestHard, forest_boss = (Elite) Fire Forest                               |
| .   city, cityHard, city_boss = (Elite) Vanquished                                      |
| .   cave, caveHard, cave_boss = (Elite) Fungus Cave                                     |
| .   dumb, dumbHard, dumb_boss = (Elite) Underground Base                                |
| .   jungle, jungleHard, jungle_boss = (Elite) Strands                                   |
| .   hulk, hulkHard, hulk_boss = (Elite) Graveyard                                       |
| .   lab, labHard, lab_boss = (Elite) Temple of the Lost                                 |
| .   sc, sc_boss = Star Cathedral                                                        |
| Since boss rooms do not have zone names, the music is used to detect it instead         |
| This means that you cannot tell the difference between a regular boss and an elite boss |
| "Hard" stands for Elite, and "_boss" stands for boss                                    |
| Secrets dont have a zone name while shops do                                            |
+-----------------------------------------------------------------------------------------+
################################################## Requirements ##################################################
+--------------------------------------------------(!N): Noise--------------------------------------------------+
| Required for:                                                                                                 |
| .   sc opening audio cue                                                                                      |
| .   sc open audio cue                                                                                         |
| Requirements:                                                                                                 |
| .   See Compiling in `README.md` for steps on how to compile the changes                                      |
| .   Add `XDL_PlaySound` to `SYMLIST` in `loader.py`                                                           |
| .   Add `typedef bool (*pXDL_PlaySound)(const char *soundName, int channel, double x, double y);` to `XDL.h`  |
| .   Recompile                                                                                                 |
+---------------------------------------------------------------------------------------------------------------+
+---------------------(!A): auraVidId---------------------+
| Required for:                                           |
| .   hiding aura                                         |
| Requirements:                                           |
| .   Add `flags::auraVidId` to `SYMLIST` in `loader.py`  |
+---------------------------------------------------------+
Change Log:
b1.0:
 - Custom Background
b1.1:
 - Mini HUD above shell
b1.2:
 - SC Close Time (!N)
b1.3:
 - EC Counter
b1.4:
 - merged code
b1.5:
 - additional noise hiding (fake vq mid shots)
b1.6:
 - server full enter spam (!I)
b1.6.1:
 - various optimisation
b1.7:
 - auto config
b1.7.1:
 - aura hide (!A)
b1.7.2:
 - instant respin (!I)
 - enter spam warning (!I)
b1.8:
 - put more code in init
 - instant down warp (!I)
b1.8.1:
 - adjusted dw instant inputs (!I)
 - input buffer exhaustion is avoided (!I)
b1.8.2:
 - added sc opening cue (!N)
b1.9:
 - removed unnecessary code
 - moved dw inputs out of onPresent ("why.") (!I)
b1.9.1:
 - added new line before close time log
b1.10:
 - added automatic downwarp bounce animation cancel (!I)
 - fixed some problems with instant respin inputting more than it should (!I)
b1.10.1:
 - Increased size of sc close time text to match what it was originally supposed to be
b1.10.2:
 - Increased default buffer value to the correct default 1000 in `self.inputKey`
 - No longer passes `cw.inputBuffer` when releasing a key (it does not affect the buffer to release a key)
b1.11:
 - Automatic inputs have been taking up space and were fully removed
 - Removed redunant `.keys()` when for looping through dicts
 - Spin timer duration is available to change in the config until the permanent solution is found
 - Rewrote console warnings for missing "XDL_PlaySound" func and "auraVidId" symbol
 - Made config options easier to understand inside the plugin (will create an official config section later)
 - Mini ammo display color can now be customised the same as mini hp color, changing when ammo is not full
 - All text has outline customisation and isnt defined by one variable
 - Added additional HUD text to display which server you entered (located below the ec counter)
 - Mini HUD text color is no longer reprocessed when the mini HUD is enabled but hp or ammo is disabled
"""


import util
import logging
import colorsys
import time

from _remote import ffi, lib
from manager import PluginBase


ELEMS = 'hp maxhp ammo maxammo spam'.split()

BACKGROUND_FLAGS = ('drawScatter', 'drawUniform')

SPIN_ANIM_IDS = {14, 19, 24, 29} # skein: 19, motley: 24, balefire: 29
WARP_ANIM_IDS = {10, 11, 12, 13} # side warp: 10, exiting side warp: 11, downwarp: 12, downwarp bounce: 13
# OTHER_ANIM_IDS = {40, 41, 42, 34, 35} # SB side: 40, SB up: 41, SB down: 42, Baetyl side / down: 34, Baetyl up: 35
# ALL_ANIM_IDS = SPIN_ANIM_IDS | WARP_ANIM_IDS

# a large number that fits in int32 and also unlikely to overflow
OFFSET = 1 << 29


def getRGB(col):
	return ((col >> 16) & 0xff) / 255, ((col >> 8) & 0xff) / 255, (col & 0xff) / 255


def getHex(red, green, blue):
	return ((int(red * 255) & 0xff) << 16) +\
		((int(green * 255) & 0xff) << 8) +\
		(int(blue * 255) & 0xff)


class Plugin(PluginBase):
	def onInit(self, inputs=None):
		# TODO: see about letting each config variable not require a restart to update (like spin_bar_side)
		# TODO: remake config vars to be generated via loop
		#  -- Custom BG -- :
		self.config.option('draw_bg', True, 'bool')
		self.config.option('change_speed', 0, 'int')
		self.config.option('base_color', 0x000000, 'color')
		#  -- Extra Hiding -- :
		self.config.option('hide_extras', True, 'bool')
		self.config.option('show_aura', True, 'bool')
		#  -- Extra HUD Info -- :
		# Mini HUD:
		self.config.option('show_mini_hud', True, 'bool')
		self.config.option('show_mini_hp', True, 'bool')
		self.config.option('x_hp', 30, 'int')
		self.config.option('y_hp', 35, 'int')
		self.config.option('size_hp', 18, 'int')
		self.config.option('size_maxhp', 14, 'int')
		self.config.option('outline_hp', 2, 'int')
		self.config.option('outline_maxhp', 2, 'int')
		self.config.option('color_hp', 0xffffffff, 'color')
		self.config.option('color_hp_full', 0xff00ff00, 'color')
		self.config.option('show_mini_ammo', True, 'bool')
		self.config.option('x_ammo', -35, 'int')
		self.config.option('y_ammo', 35, 'int')
		self.config.option('size_ammo', 14, 'int')
		self.config.option('size_maxammo', 14, 'int')
		self.config.option('outline_ammo', 2, 'int')
		self.config.option('outline_maxammo', 2, 'int')
		self.config.option('color_ammo', 0xffff80, 'color')
		self.config.option('color_ammo_full', 0xffff80, 'color')
		self.config.option('show_spam_timer', True, 'bool')
		self.config.option('x_spam', -48, 'int')
		self.config.option('y_spam', 50, 'int')
		self.config.option('size_spam', 14, 'int')
		self.config.option('outline_spam', 2, 'int')
		self.config.option('color_spam', 0xffff80, 'color')
		# EC Counter:
		self.config.option('show_ec_counter', True, 'bool')
		self.config.option('x_ec', 120, 'int')
		self.config.option('y_ec', 165, 'int')
		self.config.option('size_ec', 12, 'int')
		self.config.option('outline_ec', 3, 'int')
		self.config.option('color_ec', 0xf0f0f0, 'color')
		self.config.option('font_ec', 'HemiHeadBold', 'str')
		# DW Spin Bar:
		self.config.option('show_spin_bar', True, 'bool')
		self.config.option('spin_bar_y', 10, 'int')
		self.config.option('spin_bar_width', 90, 'int')
		self.config.option('spin_bar_height', 4, 'int')
		self.config.option('spin_bar_side', 3, 'int')
		self.config.option('warn_percent', 30, 'int')
		self.config.option('spin_duration', 800, 'int')  # ;-; one day
		self.config.option('spin_bar_background', 0xff000000, 'color')
		self.config.option('spin_bar_background_warn', 0xff8080, 'color')
		self.config.option('spin_bar_outline', 0xff808080, 'color')
		self.config.option('spin_bar_color', 0xffff80, 'color')
		# Server Reminder:
		self.config.option('show_server', True, 'bool')
		self.config.option('x_server', 120, 'int')
		self.config.option('y_server', 200, 'int')
		self.config.option('size_server', 12, 'int')
		self.config.option('outline_server', 3, 'int')
		self.config.option('color_server', 0xf0f0f0, 'color')
		self.config.option('font_server', 'HemiHeadBold', 'str')
		#  -- SC Close Timer -- :
		self.config.option('show_sc_time', True, 'bool')
		self.config.option('play_sc_audio_cue', True, 'bool')
		self.config.option('sc_close_timer_duration', 20, 'int')


		# text classes
		for name in ELEMS:
			setattr(self, 'txt_' + name, util.PlainText())
		self.sc_open_time = util.MultilineText(size=24)  # TODO: make PlainText?
		self.txt_ec = util.MultilineText(size=self.config.size_ec, outlineSize=self.config.outline_ec,
			font=self.config.font_ec, color=self.config.color_ec)
		self.txt_ec.text = '+0 EC\n+0 EC Total'
		self.txt_server = util.PlainText(size=self.config.size_server, outlineSize=self.config.outline_server,
			font=self.config.font_server, color=self.config.color_server)
		self.txt_server.text = "Server: n/a"

		self.currTime = self.prevTime = time.perf_counter()
		self.hidden = []
		self.hsv = None
		self.ec_init = True
		self.draw_hud = False
		self.noise_enabled = False
		self.aura_enabled = False
		self.sc_open = False
		self.draw_ec = False
		self.home = False
		self.run_auto_config = False
		# self.forcing_bg_flags = False
		self.played_cue = False
		self.draw_server = False
		self.cc = 0
		self.entering_ec = 0
		self.starting_ec = 0
		self.game_open_time = -600
		self.lastVal = 'True'
		self.last_zone = b''

		# prep auto config
		self.auto_configs = {}
		for desc, val in self.config._section.items():
			desc = desc.split()
			if len(desc) <3: continue
			pname, opt, zone = desc
			args = {
				'plugin': 'plugin_' + pname,
				'option': opt,
				'value': val
			}
			if zone not in self.auto_configs:
				self.auto_configs[zone] = []
			self.auto_configs[zone].append(args)

		# check if noise can be enabled
		if 'XDL_PlaySound' not in self.refs:
			self.noise_enabled = False
			logging.warn('Warning: `remote.py` has not been compiled with the "XDL_PlaySound" function.  '
				'Noise related plugin features disabled.  See Alexrns or the top of this plugin for details.')
		else: self.noise_enabled = True
		# check for aura symbol
		if 'auraVidId' not in self.refs:
			logging.warn('Warning: the "auraVidId" symbol is not in "self.refs", cannot hide aura.  '
				'Has "flags::auraVidId" been added to "SYMLIST" in `loader.py`?')
		else:
			self.aura_enabled = True

		# finalizing some variables
		if self.config.spin_bar_side in {1, 3}:
			self.spin_bar_width = self.config.spin_bar_height
			self.spin_bar_height = self.config.spin_bar_width
		else:
			self.spin_bar_width = self.config.spin_bar_width
			self.spin_bar_height = self.config.spin_bar_height
		if self.spin_bar_width <= 0: self.spin_bar_width = 1
		if self.spin_bar_height <= 0: self.spin_bar_height = 1

		recalc_base_color = False
		if self.config.change_speed > 0:
			r, g, b = getRGB(self.config.base_color)
			h, s, v = colorsys.rgb_to_hsv(r, g, b)
			if s == 0:
				s = .65
				logging.warn('Planning to change Hue, but Saturation = 0. Defaulting Saturation to 65')
				recalc_base_color = True
			if v == 0:
				v = .7
				logging.warn('Planning to change Hue, but Value = 0. Defaulting Value to 70')
				recalc_base_color = True
			if recalc_base_color:
				logging.info('Chosen Base RGB: ({}, {}, {})'.format(int(r * 255), int(g * 255), int(b * 255)))
				r, g, b = colorsys.hsv_to_rgb(h, s, v)
				logging.info('New Base RGB: ({}, {}, {})'.format(int(r * 255), int(g * 255), int(b * 255)))
				self.config.base_color = getHex(r, g, b)
		r, g, b = getRGB(self.config.base_color)
		h, s, v = colorsys.rgb_to_hsv(r, g, b)
		self.hsv = (h, s, v)

		'''
		self.prev_bg_flags = dict()
		for opt in BACKGROUND_FLAGS:
			self.prev_bg_flags[opt] = 'no'
		'''

	def beforeUpdate(self, inputs=None):
		self.prevTime = self.currTime
		self.currTime = time.perf_counter()
		self.timeDiff = self.currTime - self.prevTime

		if self.refs.ClientWorld == ffi.NULL: self.run_auto_config = True

		self.draw_hud = self.draw_ec = self.draw_spam = self.draw_server = False


	def afterUpdate(self, inputs=None):
		'''Test bg flag forcing
		plugs = self.refs.manager._active
		conf = plugs['plugin_misc'].config
		if not self.config.draw_bg:
			if not self.forcing_bg_flags:
				self.forcing_bg_flags = True
				logging.info('---more_misc---')
				for opt in BACKGROUND_FLAGS:
					# logging.info(conf._section[opt])
					self.prev_bg_flags[opt] = conf._section[opt]
					conf._section[opt] = 'False'
					if opt in conf._cache:
						del conf._cache[opt]
				for opt in BACKGROUND_FLAGS:
					logging.info(f'1 {conf._section[opt]}')
				logging.info(self.prev_bg_flags)
		else:
			if self.forcing_bg_flags:
				self.forcing_bg_flags = False
				logging.info('---more_misc---')
				for opt in BACKGROUND_FLAGS:
					conf._section[opt] = self.prev_bg_flags[opt]
					if opt in conf._cache:
						del conf._cache[opt]
				for opt in BACKGROUND_FLAGS:
					logging.info(f'2 {conf._section[opt]}')
				logging.info(self.prev_bg_flags)
		'''

		mm = self.refs.MainMenu
		if mm != ffi.NULL:
			sName = mm.serverName
			if sName != ffi.NULL:
				self.txt_server.text = f'Server: {util.getstr(sName.value)}'

		gc = self.refs.GameClient
		if gc == ffi.NULL: return

		if not self.sc_open:
			chat_list = util.vec2list(gc.chatLog.entries, 'struct ChatLogEntry *')
			if chat_list:
				chat_msg = ffi.string(chat_list[-1].chat.message.s)
				chat_type = chat_list[-1].chat.chattype
				if chat_type == 4 and chat_msg == b'A portal to the Star Cathedral has opened!':

					# close_start_time = time.localtime()[5] + time.localtime()[4] * 60 + 1200
					# close_end_time = close_start_time + 90
					# close_start_sec = str(close_start_time % 60).zfill(2)
					# close_start_min = str(close_start_time // 60).zfill(2)
					# close_end_sec = str(close_end_time % 60).zfill(2)
					# close_end_min = str(close_end_time // 60).zfill(2)

					open_sec = time.localtime()[5]
					open_min = time.localtime()[4]
					close_start_sec = str(open_sec).zfill(2)
					close_start_min = str((open_min + 20) % 60).zfill(2)
					close_finish_sec = str((open_sec + 30) % 60).zfill(2)
					close_finish_min = str((open_min + 21 + ((open_sec + 30) // 60)) % 60).zfill(2)

					self.sc_open_time.text = 'closing: XX:{}:{}'.format(close_start_min, close_start_sec)
					logging.info('\nLast port: XX:{0}:{1}    closing: XX:{0}:{1} - XX:{2}:{3}'.format(
						close_start_min, close_start_sec, close_finish_min, close_finish_sec))
					self.game_open_time = time.perf_counter()
					self.sc_open = self.draw_sc = True
					if self.noise_enabled and self.config.play_sc_audio_cue:
						self.refs.XDL_PlaySound(b'ui.buttonclick', 0, 0, 0)

		cw = self.refs.ClientWorld
		if cw == ffi.NULL: return

		plugs = self.refs.manager._active
		conf = plugs['plugin_misc'].config
		if not self.config.draw_bg:
			if self.config.change_speed > 0:
				h, s, v = self.hsv
				h += self.cc
				self.cc += ((max(0, min(20, self.config.change_speed)) * self.timeDiff) / 100) % 1
				r, g, b = colorsys.hsv_to_rgb(h, s, v)
				bg = getHex(r, g, b)
			else: bg = self.config.base_color
			self.refs.stage[0].backgroundColor = bg
			if self.lastVal == 'True':
				for opt in BACKGROUND_FLAGS:
					conf._section[opt] = self.lastVal = 'False'
					if opt in conf._cache:
						del conf._cache[opt]
		elif self.config.draw_bg:
			if self.lastVal == 'False':
				for opt in BACKGROUND_FLAGS:
					conf._section[opt] = self.lastVal = 'True'
					if opt in conf._cache:
						del conf._cache[opt]
					self.cc = 0

		if self.run_auto_config:
			self.run_auto_config = False
			cwprops = cw.asWorld.props
			zone = util.getstr(cwprops.zone) or util.getstr(cwprops.music)
			if zone in self.auto_configs:
				for args in self.auto_configs[zone]:
					pname = args['plugin']
					if pname not in plugs: continue
					conf = plugs[pname].config
					opt = args['option']
					val = args['value']
					if val != None:
						conf._section[opt] = val
						if opt in conf._cache:
							del conf._cache[opt]

		finished_deposits = 0
		for obj in util.worldobjects(util.clientServerSubWorld(cw)):
			if self.config.hide_extras: # need more ideas
				if ffi.string(obj.props.vid.s) == b'city.hbshot':
					self.hide(obj)
			if ffi.string(obj.props.vid.s) == b'lobby.keydropdone':
				finished_deposits += 1
		if self.noise_enabled and not self.played_cue:
			if finished_deposits == 8 and not self.sc_open and self.config.play_sc_audio_cue:
				self.played_cue = True
				self.refs.XDL_PlaySound(b'ui.buttonclick', 0, 0, 0)

		plr = util.clientPlayer(cw)
		if plr == ffi.NULL: return
		plr_name = util.getClassName(plr)
		pprops = ffi.cast('struct WorldObject *', plr).props

		if self.config.show_mini_hud:
			if plr_name in self.refs.CASTABLE['PlayerCharacter']:
				if self.config.show_mini_hp:
					self.txt_hp.text = '{}'.format(pprops.hitpoints)
					self.txt_maxhp.text = '/{}'.format(pprops.maxhitpoints)
					if pprops.hitpoints == pprops.maxhitpoints: hpcolor = self.config.color_hp_full
					else: hpcolor = self.config.color_hp
					self.txt_hp.color = self.txt_maxhp.color = hpcolor
				if self.config.show_mini_ammo:
					ammo = util.playerField(plr, 'ammo')
					max_ammo_base, max_ammo_bonus = util.playerStatValues(
						plr, 'maxAmmo')
					max_ammo = max_ammo_base + max_ammo_bonus
					ammo_mult = util.playerField(plr, 'ammoMult')
					self.txt_ammo.text = '{}'.format(ammo)
					if ammo_mult > 1: self.txt_maxammo.text = '/{} (x{})'.format(max_ammo, ammo_mult)
					else: self.txt_maxammo.text = '/{}'.format(max_ammo)
					if ammo == max_ammo: ammocolor = self.config.color_ammo_full
					else: ammocolor = self.config.color_ammo
					self.txt_ammo.color = self.txt_maxammo.color = ammocolor
				if self.config.show_spam_timer:
					if ffi.string(cw.asWorld.props.music.s) in {b'lobby', b'home'}:
						self.draw_spam = True
						spam_timer = util.playerField(plr, 'secondarySpamTimer')
						self.txt_spam.text = str(round(spam_timer / 1000, 1))
						self.txt_spam.color = self.config.color_spam

				for name in ELEMS:
					el = getattr(self, 'txt_' + name)
					el.size = getattr(self.config, 'size_' + name)
					el.outlineSize = getattr(self.config, 'outline_' + name)

				self.draw_hud = True

		if self.config.show_ec_counter:
			zone = ffi.string(cw.asWorld.props.zone.s) or ffi.string(cw.asWorld.props.music.s)
			ec = util.playerField(plr, 'ec')
			if self.ec_init:
				self.ec_init = False
				self.home = True
				self.entering_ec = self.starting_ec = ec
				self.last_zone = zone
			if zone in {b'lobby', b'home'}:
				if not self.home: self.home = True
			else:
				if self.home:
					self.home = False
					self.entering_ec = ec
					self.last_zone = zone
				ec_diff = ec - self.entering_ec
				self.txt_ec.text = '{} EC last {}\n{} EC Total'.format(
					ec_diff, self.last_zone.decode('utf-8'), ec - self.starting_ec)
			self.txt_ec.size = self.config.size_ec
			self.txt_ec.outlineSize = self.config.outline_ec
			self.txt_ec.font = self.config.font_ec
			self.txt_ec.color = self.config.color_ec
			self.draw_ec = True

		if self.config.show_server:
			self.draw_server = True

		if self.aura_enabled:
			if self.config.show_aura:
				self.refs.auraVidId[0] = 0
			else:
				self.refs.auraVidId[0] = 1

	def onPresent(self, inputs=None):
		for obj in self.hidden:
			obj.props.xmp += OFFSET
		self.hidden.clear()

		if self.draw_hud:
			cw = self.refs.ClientWorld
			wv = self.refs.WorldView
			plr = util.clientPlayer(cw)
			pprops = ffi.cast('struct WorldObject *', plr).props
			hp = pprops.hitpoints
			maxhp = pprops.maxhitpoints

			x = pprops.xmp // 256 - wv.offset.x
			y = pprops.ymp // 256 - wv.offset.y
			textx = (x + pprops.wmp / 512) / self.refs.scaleX
			texty = y / self.refs.scaleY

			# hp
			if self.config.show_mini_hp:
				hpX = textx - self.config.x_hp
				hpY = texty - self.config.y_hp
				self.txt_hp.draw(hpX, hpY, anchorX=1)
				self.txt_maxhp.draw(hpX - 2, hpY)

			# ammo
			if self.config.show_mini_ammo:
				ammoX = textx - self.config.x_ammo
				ammoY = texty - self.config.y_ammo
				self.txt_ammo.draw(ammoX, ammoY, anchorX=1)
				self.txt_maxammo.draw(ammoX - 2, ammoY)

			# spam
			if self.config.show_spam_timer and self.draw_spam:
				spamX = textx - self.config.x_spam
				spamY = texty - self.config.y_spam
				self.txt_spam.draw(spamX, spamY, anchorX=1)

			# could do loop?
			'''
			for val in ('hp', 'ammo', 'spam'):
				x = getattr(self.config, 'x_' + val)
				y = getattr(self.config, 'y_' + val)
				getattr(self, 'txt_' + val).draw(x, y, anchorX=1)
				if val != 'spam':
					getattr(self, 'txt_' + val + 'max').draw(x - 2, y)
			'''
			if self.config.show_spin_bar:
				aprops = pprops.animprops
				if aprops != ffi.NULL:
					if util.getClassName(plr) == 'Duskwing':
						animid = aprops.animid
						if animid in SPIN_ANIM_IDS:
							bw = self.spin_bar_width
							bh = self.spin_bar_height

							bmax = self.config.spin_duration
							bcurr = abs(aprops.pos - bmax)
							bp = bcurr / bmax

							if bp <= self.config.warn_percent / 100:
								bg_color = self.config.spin_bar_background_warn
							else: bg_color = self.config.spin_bar_background

							if self.config.spin_bar_side == 1:
								bh = -bh
								bx = (x + pprops.wmp / 256) / self.refs.scaleX + self.config.spin_bar_y
								by = (y + pprops.hmp / 512) / self.refs.scaleY - bh / 2
								currW = bw
								currH = bp * bh
							elif self.config.spin_bar_side == 2:
								bx = (x + pprops.wmp / 512) / self.refs.scaleX - bw / 2
								by = (y + pprops.hmp / 256) / self.refs.scaleY + self.config.spin_bar_y
								currW = bp * bw
								currH = bh
							elif self.config.spin_bar_side == 3:
								bh = -bh
								bx = x / self.refs.scaleX - bw - self.config.spin_bar_y
								by = (y + pprops.hmp / 512) / self.refs.scaleY - bh / 2
								currW = bw
								currH = bp * bh
							else:
								bx = (x + pprops.wmp / 512) / self.refs.scaleX - bw / 2
								by = y / self.refs.scaleY - bh - self.config.spin_bar_y
								currW = bp * bw
								currH = bh

							cw_ = self.refs.canvasW_[0]
							ch_ = self.refs.canvasH_[0]
							self.refs.canvasW_[0] = self.refs.windowW
							self.refs.canvasH_[0] = self.refs.windowH
							self.refs.XDL_FillRect(
								round(bx) - 1, round(by) - 1, round(bw) + 2, round(bh) + 2,
								self.config.spin_bar_outline, lib.BLENDMODE_BLEND)
							self.refs.XDL_FillRect(
								round(bx), round(by), round(bw), round(bh),
								bg_color, lib.BLENDMODE_BLEND)
							self.refs.XDL_FillRect(
								round(bx), round(by), round(currW), round(currH),
								self.config.spin_bar_color, lib.BLENDMODE_BLEND)
							self.refs.canvasW_[0] = cw_
							self.refs.canvasH_[0] = ch_

		if self.config.show_sc_time:
			if self.currTime - self.game_open_time < self.config.sc_close_timer_duration:
				self.sc_open_time.draw(400, 200)

		if self.draw_ec:
			self.txt_ec.draw(self.config.x_ec, self.config.y_ec, anchorX=0.5)

		if self.draw_server:
			self.txt_server.size = self.config.size_server
			self.txt_server.outlineSize = self.config.outline_server
			self.txt_server.font = self.config.font_server
			self.txt_server.color = self.config.color_server
			self.txt_server.draw(self.config.x_server, self.config.y_server, anchorX=0.5)

	def hide(self, obj):
		obj.props.xmp -= OFFSET
		self.hidden.append(obj)