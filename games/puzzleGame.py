﻿"""
Controller components of the Puzzle game
"""

# Vizard modules
import viz
import vizact, viztask, vizproximity
import vizmat
import vizshape

# Python built-in modules
import random
import math
import numpy
import json, csv
import time, datetime
import threading
import time

# Custom modules
import init
import menu
import config
import model
import puzzleView
import bp3d

class PuzzleController(object):
	"""
	Puzzle game controller base class. Not intended to be used directly, derive
	children that feature the game mode functionality you want.
	"""
	def __init__(self):
		self.modeName = ''
		
		self._maxThreads = 40
		self._curThreads = 0
		
		self._meshes		= []
		self._meshesById	= {}
		self._keystones		= []
		self._proximityList	= []
		self._keyBindings	= []
		self._inRange		= []
		
		self._boneInfo		= None
		self._closestBoneIdx = None
		self._prevBoneIdx	= None
		self._lastGrabbed	= None
		self._highlighted	= None
		self._gloveLink		= None

		self._grabFlag		= False
		self._snapAttempts	= 0
		self._imploded		= False
		
		self._pointerTexture = model.pointer.getTexture()
		self._pointerOrigColor = model.pointer.getColor()

		self.viewcube = puzzleView.viewCube()
		
	def load(self, dataset):
		"""
		Load datasets and initialize everything necessary to commence
		the puzzle game.
		"""
		
		# Dataset
		model.ds = bp3d.DatasetInterface()

		# Proximity management
		model.proxManager = vizproximity.Manager()
		target = vizproximity.Target(model.pointer)
		model.proxManager.addTarget(target)

		model.proxManager.onEnter(None, self.EnterProximity)
		model.proxManager.onExit(None, self.ExitProximity)
	
		#Setup Key Bindings
		self.bindKeys()
		
		# start the clock
		time.clock()

		self.score = PuzzleScore(self.modeName)
		
#		viztask.schedule(soundTask(glove))

		self._meshesToLoad = model.ds.getOntologySet(dataset)
		viztask.schedule(self.loadControl(self._meshesToLoad))
		
	def loadControl(self, meshes = [], animate = False):
		"""control loading of meshes --- used to control multithreading"""
		yield self.loadMeshes(meshes)
		self.setKeystone()
		for m in self._meshes:
#			if (m.group.grounded):
#				#Hardcoded keystone
#				m.setPosition(m.center)
#				m.setEuler([0.0,90.0,180.0]) # [0,0,180] flip upright [0,90,180] flip upright and vertical		
			# b.setPosition([(random.random()-0.5)*3, 1.0, (random.random()-0.5)*3]) # random sheet, not a donut
			if not m.group.grounded:
				angle	= random.random() * 2 * math.pi
				radius	= random.random() + 1.5
				
				targetPosition	= [math.sin(angle) * radius, 1.0, math.cos(angle) * radius]
				targetEuler		= [0.0,90.0,180.0]
				#targetEuler	= [(random.random()-0.5)*40,(random.random()-0.5)*40 + 90.0, (random.random()-0.5)*40 + 180.0]
				
				if (animate):
					move = vizact.moveTo(targetPosition, time = 2)
					spin = vizact.spinTo(euler = targetEuler, time = 2)
					transition = vizact.parallel(spin, move)
					m.addAction(transition)
				else:					
					m.setPosition(targetPosition)
					m.setEuler(targetEuler)
			m.addSensor()
			m.addToolTip()
	
#		Check to make sure that all requested meshes were loaded if they aren't then load the missing meshes
		lingeringThreads = 0
		while True:
			if lingeringThreads >= 20:
				self.printNoticeable('Error: Issue with loading, not everything was loaded, going to load the remaining meshes')
				needToLoad = list(set(self._meshesToLoad) - set(self._meshes))
				self.loadControl(needToLoad)
				break
			if len(self._meshes) < len(self._meshesToLoad)- self.unknownFiles:
				self.printNoticeable('notice: some threads are still running, please wait')
			else:
				self.printNoticeable('notice: All Items Were Loaded!')
				break
			yield viztask.waitTime(0.2)
			lingeringThreads += 1

	def loadMeshes(self, meshes = [], animate = False):
		"""Load all of the files from the dataset into puzzle.mesh instances"""
		self.unknownFiles = 0
		model.threads = 0
		self.printNoticeable('start of rendering process')
		for i, fileName in enumerate(meshes):
			# This is the actual mesh we will see
			if not model.ds.getMetaData(file = fileName):
				print "WARNING, UNKNOWN FILE ", fileName
				self.unknownFiles += 1
				continue
			#Wait to add thread if threadThrottle conditions are not met
			model.threads += 1 #Add 1 for each new thread added --- new render started
			yield viztask.waitTrue(self.threadThrottle,self._maxThreads, model.threads)
			yield viz.director(self.renderMeshes, fileName)
		self.printNoticeable('end of rendering process')
	
	def renderMeshes(self, fileName):
		"""Creates a mesh class instance of the mesh fileName"""
		m = bp3d.Mesh(fileName)
		
		self._meshes.append(m)
		self._meshesById[m.id] = m
		
		model.threads -= 1 #Subtract 1 for each thread that has finished rendering
		
	def threadThrottle(self, maxThreads, curThreads, threadFlag = True):
		"""If the number of current threads (curThreads) is greater than the decided maximum, then 
		returns false --- and vice-versa"""
		while threadFlag:
			if curThreads <= maxThreads:
				threadFlag = False
			else:
				threadFlag = True
		return True
	
	def setKeystone(self):
		# Set Keystone
		for m in [self._meshes[i] for i in range(0,1)]:
			cp = m.centerPointScaled
			cp = [cp[0], -cp[2] + 0.150, cp[1]]
			m.setPosition(cp, viz.ABS_GLOBAL)
			m.setEuler([0.0,90.0,180.0])
			m.group.grounded = True
			self._keystones.append(m)
		#snapGroup(smallBoneGroups)

	def printNoticeable(self, text):
		print '-'*len(text)
		print text.upper()
		print '-'*len(text)
		

	def unloadBones(self):
		"""Unload all of the bone objects to reset the puzzle game"""
		for m in self._meshes:
			print 'removing ', m.name
			m.remove(children = True)
		
	def transparency(self, source, level, includeSource = False):
		"""Set the transparency of all the bones"""
		meshes = self._meshes
		if includeSource:
			for b in meshes:
				b.setAlpha(level)
		else:
			for b in [b for b in meshes if b != source]:
				b.setAlpha(level)			

	def moveCheckers(self, sourceChild):
		"""
		Move all of the checker objects on each bone into position, in order to
		see if they should be snapped.
		"""
		source = self._meshesById[sourceChild.id] # Just in case we pass in a node3D
		
		for bone in [b for b in self._meshes if b != source]:
			bone.checker.setPosition(source.centerPoint, viz.ABS_PARENT)

	def getAdjacent(self, mesh, pool):
		"""Sort pool by distance from mesh"""
		self.moveCheckers(mesh)
		neighbors = []
		
		for m in pool:
			centerPos = m.getPosition(viz.ABS_GLOBAL)
			checkerPos = m.checker.getPosition(viz.ABS_GLOBAL)
			dist = vizmat.Distance(centerPos, checkerPos)	
			neighbors.append([m,dist])
		
		sorted(neighbors, key = lambda a: a[1])
		
		return [l[0] for l in neighbors]
		
	def snapCheck(self):
		"""
		Snap checks for any nearby bones, and mates a src bone to a dst bone
		if they are in fact correctly placed.
		"""
		if not self.getSnapSource():
			print 'nothing to snap'
			return

		SNAP_THRESHOLD	= 0.5;
		DISTANCE_THRESHOLD = 1.5;
		ANGLE_THRESHOLD	= 45;
		sourceMesh		= self.getSnapSource()
		targetMesh		= self.getSnapTarget()
		searchMeshes	= self.getSnapSearch()
		
		self.moveCheckers(sourceMesh)
			
		# Search through all of the checkers, and snap to the first one meeting our snap
		# criteria
		
		if self._snapAttempts >= 3 and not sourceMesh.group.grounded:
			self.snap(sourceMesh, targetMesh, children = True)
			viz.playSound(".\\dataset\\snap.wav")
			print 'Three unsuccessful snap attempts, snapping now!'
			self.score.event(event = 'autosnap', description = 'Three unsuccessful snap attempts, snapping now!', \
				source = sourceMesh.name, destination = targetMesh.name)
			self._snapAttempts = 0
			if self.modeName == 'testplay':
				self.pickSnapPair()
		elif sourceMesh.group.grounded:
			print 'That object is grounded. Returning!'
		else:
			for bone in [b for b in searchMeshes if b not in sourceMesh.group.members]:
				targetSnap = bone.checker.getPosition(viz.ABS_GLOBAL)
				targetPosition = bone.getPosition(viz.ABS_GLOBAL)
				targetQuat = bone.getQuat(viz.ABS_GLOBAL)
				
				currentPosition = sourceMesh.getPosition(viz.ABS_GLOBAL)
				currentQuat = sourceMesh.getQuat(viz.ABS_GLOBAL)		
				
				snapDistance = vizmat.Distance(targetSnap, currentPosition)
				proximityDistance = vizmat.Distance(targetPosition, currentPosition)
				angleDifference = vizmat.QuatDiff(bone.getQuat(), sourceMesh.getQuat())
				
				if (snapDistance <= SNAP_THRESHOLD) and (proximityDistance <= DISTANCE_THRESHOLD) \
						and (angleDifference < ANGLE_THRESHOLD):
					print 'Snap! ', sourceMesh, ' to ', bone
					self.score.event(event = 'snap', description = 'Successful snap', source = sourceMesh.name, destination = bone.name)
					viz.playSound(".\\dataset\\snap.wav")
					self.snap(sourceMesh, bone, children = True)
					if self.modeName == 'testplay':
						self.pickSnapPair()
					break
			else:
				print 'Did not meet snap criteria!'
				self._snapAttempts += 1
				self.score.event(event = 'snapfail', description = 'did not meet snap criteria', source = sourceMesh.name)
		if len(self._meshes) == len(sourceMesh.group.members):
			print "Assembly completed!"
			end()
			menu.ingame.endButton()

	def snap(self, sourceMesh, targetMesh, children = False):
		self.moveCheckers(sourceMesh)
		if children:
			sourceMesh.setGroupParent()
		sourceMesh.moveTo(targetMesh.checker.getMatrix(viz.ABS_GLOBAL))
		targetMesh.group.merge(sourceMesh)
		if sourceMesh.group.grounded:
			self._keystones.append(sourceMesh)
	
	def getSnapSource(self):
		"""Define source object for snapcheck"""
		return self._lastGrabbed
	
	def getSnapTarget(self):
		"""Define target object for snapcheck"""
		return self.getAdjacent(self._lastGrabbed, self.getEnabled())[0]
		
	def getSnapSearch(self):
		"""Define list of objects to search for snapcheck"""
		return self.getEnabled()
	
	def snapGroup(self, boneNames):
		"""Specify a list of bones that should be snapped together"""
		print boneNames
		if (len(boneNames) > 0):
			meshes = []
			[[meshes.append(self._meshesById[m]) for m in group] for group in boneNames]
			[m.snap(meshes[0], animate = False) for m in meshes[1:]]

	def grab(self):
		"""Grab in-range objects with the pointer"""
		grabList = self._proximityList # Needed for disabling grab of grounded bones
		
		if len(grabList) > 0 and not self._grabFlag:
			target = self.getClosestBone(model.pointer,grabList)
			
			if target.group.grounded:
				target.color([0,1,0.5])
				target.tooltip.visible(viz.ON)
			else:
				target.setGroupParent()
				self._gloveLink = viz.grab(model.pointer, target, viz.ABS_GLOBAL)
				self.score.event(event = 'grab', description = 'Grabbed bone', source = target.name)
				self.transparency(target, 0.7)
				target.color([0,1,0.5])
				target.tooltip.visible(viz.ON)
				
			if target != self._lastGrabbed and self._lastGrabbed:
				self._lastGrabbed.color(reset = True)
				self._lastGrabbed.tooltip.visible(viz.OFF)
				for m in self._proximityList: 
					if m == self._lastGrabbed:
						self._lastGrabbed.color([1.0,1.0,0.5])
			self._lastGrabbed = target
		self._grabFlag = True

	def release(self):
		"""
		Release grabbed object from pointer
		"""
		if self._gloveLink:
			self.transparency(self._lastGrabbed, 1.0)
			self._gloveLink.remove()
			self._gloveLink = None
			self.score.event(event = 'release')
		self._grabFlag = False
	
	def getDisabled(self):
		return [m for m in self._meshes if not m.getEnabled()]
		
	def getEnabled(self, includeGrounded = True):
		if includeGrounded:
			return [m for m in self._meshes if m.getEnabled()]
		else:
			return [m for m in self._meshes if m.getEnabled() if not m.group.grounded]		

	def getClosestBone(self, pointer, proxList):
		"""
		Looks through proximity list and searches for the closest bone to the glove and puts it at
		the beginning of the list
		"""
		if(len(proxList) >0):
			bonePos = proxList[0].getPosition(viz.ABS_GLOBAL)
			pointerPos = pointer.getPosition(viz.ABS_GLOBAL)
			shortestDist = vizmat.Distance(bonePos, pointerPos)	
			
			for i,x in enumerate(proxList):
				bonePos = proxList[i].getPosition(viz.ABS_GLOBAL)
				pointerPos = pointer.getPosition(viz.ABS_GLOBAL)
				tempDist = vizmat.Distance(bonePos,pointerPos)
				
				if(tempDist < shortestDist):
					shortestDist = tempDist
					tempBone = proxList[i]
					proxList[i] = proxList[0]
					proxList[0] = tempBone
		return proxList[0]

	def EnterProximity(self, e):
		"""Callback for a proximity entry event between the pointer and a mesh"""
		source = e.sensor.getSourceObject()
		model.pointer.color([4.0,1.5,1.5])
		obj = self._meshesById[source.id]
		if source != self._lastGrabbed:
			obj.mesh.color([1.0,1.0,0.5])
			obj.setNameAudioFlag(1)
		self._proximityList.append(source)
	
	def ExitProximity(self, e):
		"""Callback for a proximity exit event between the pointer and a mesh"""
		source = e.sensor.getSourceObject()
		if len(self._proximityList) and not self._gloveLink:
			model.pointer.color(1,1,1)
		if source != self._lastGrabbed:
			self._meshesById[source.id].color(reset = True)
			self._meshesById[source.id].setNameAudioFlag(0)
		self._proximityList.remove(source)
	
	def implode(self):
		"""Move bones to solved positions"""
		target = self._keystones[0] #keystone
		for m in self._meshes[1:]:
			if m.getAction():
				return
			for bone in [b for b in self._meshes if b != m]:
				bone.checker.setPosition(m.centerPoint, viz.ABS_PARENT)
			m.storeMat()
			m.moveTo(target.checker.getMatrix(viz.ABS_GLOBAL), time = 0.6)
		self._imploded = True
		self._keyBindings[3].setEnabled(viz.OFF)  #disable snap key down event

	def explode(self):
		"""Move bones to position before implode was called"""
		for m in self._meshes[1:]:
			if m.getAction():
				return
			m.moveTo(m.loadMat(), time = 0.6)
		self._imploded = False
		self._keyBindings[3].setEnabled(viz.ON) #enable snap key down event

	def solve(self):
		"""Operator used to toggle between implode and explode"""
		if self._imploded == False:
			self.implode()
		else:
			self.explode()

	def end(self):
		"""Do everything that needs to be done to end the puzzle game"""
		print "Puzzle instance ending!"
#		self.score.close()
		model.proxManager.clearSensors()
		model.proxManager.clearTargets()
		model.proxManager.remove()
		self.unloadBones()
		for bind in self._keyBindings:
			bind.remove()

	def bindKeys(self):
		self._keyBindings.append(vizact.onkeydown('o', model.proxManager.setDebug, viz.TOGGLE)) #debug shapes
		self._keyBindings.append(vizact.onkeydown(' ', self.grab)) #space select
		self._keyBindings.append(vizact.onkeydown('65421', self.grab)) #numpad enter select
		self._keyBindings.append(vizact.onkeydown(viz.KEY_ALT_R, self.snapCheck))
		self._keyBindings.append(vizact.onkeydown(viz.KEY_ALT_L, self.snapCheck))
		self._keyBindings.append(vizact.onkeydown('65460', self.viewcube.toggleModes)) # Numpad '4' key
		self._keyBindings.append(vizact.onkeydown(viz.KEY_CONTROL_R, self.solve))
		self._keyBindings.append(vizact.onkeydown(viz.KEY_CONTROL_L, self.solve))
		self._keyBindings.append(vizact.onkeyup(' ', self.release))
		self._keyBindings.append(vizact.onkeyup('65421', self.release))
				
	def alphaSliceUpdate(self):
		"""This is the loop to get run on every frame to compute the alpha slice feature"""
		maxAlpha	= 1.00
		minAlpha	= 0.09
		topPlane	= 0.00005
		bottomPlane	= -0.0005
		
		while True:
			yield viztask.waitFrame(2)
			planePoint	= model.planeVert.Vertex(0).getPosition(viz.ABS_GLOBAL)
			planeNorm	= model.planeVert.Vertex(0).getNormal(viz.ABS_GLOBAL)
			for mesh in self._meshes:
				dist = planeProj(planePoint, planeNorm, mesh.getPosition(viz.ABS_GLOBAL))
				if dist >= topPlane:
					mesh.setAlpha(minAlpha)
				elif dist >= bottomPlane:
					distPercentage = 1 - ((dist - bottomPlane) / (topPlane - bottomPlane))
					mesh.setAlpha((distPercentage * (maxAlpha - minAlpha)) + minAlpha)
				else:
					mesh.setAlpha(maxAlpha)
	
	def enableSlice(self):
		viztask.schedule(self.alphaSliceUpdate())
			
		
class FreePlay(PuzzleController):
	"""Free play mode allowing untimed, unguided exploration of the selected dataset(s)"""
	def __init__(self):
		super(FreePlay, self).__init__()
		self.modeName = 'freeplay'
		
		self.enableSlice()

class TestPlay(PuzzleController):
	"""
	Assembly test play mode where the user is tasked with assembling the dataset
	in a specific order based off of a provided prompt.
	"""
	def __init__(self):
		super(TestPlay, self).__init__()
		self.modeName = 'testplay'
		
		self._meshesDisabled	= []
		self._keystoneAdjacent	= {}
		
		self._quizSource = None
		self._quizTarget = None
	
	def implode(self):
		"""Override to disable"""
		pass
		
	def explode(self):
		"""Override to disable"""
		pass
		
	def load(self, dataset = 'right arm'):
		"""
		Load datasets and initialize everything necessary to commence
		the puzzle game. Customized for test mode.
		"""
		
		# Dataset
		model.ds = bp3d.DatasetInterface()
		
		self._quizPanel = puzzleView.TestSnapPanel()
		self._quizPanel.toggle()

		# Proximity management
		model.proxManager = vizproximity.Manager()
		target = vizproximity.Target(model.pointer)
		model.proxManager.addTarget(target)

		model.proxManager.onEnter(None, self.EnterProximity)
		model.proxManager.onExit(None, self.ExitProximity)
	
		# Setup Key Bindings
		self.bindKeys()
		
		# Start the clock
		time.clock()

		self.score = PuzzleScore(self.modeName)
		
#		viztask.schedule(soundTask(glove))
		self._meshesfToLoad = model.ds.getOntologySet(dataset)
		self.loadControl(self._meshesToLoad)
		# Hide all of the meshes
		for m in self._meshes:
			m.disable()
		
		# Randomly select keystone(s)
		rand = random.sample(self._meshes, 3)
		print rand
		self._keystones += rand
		rand[0].enable()
		rand[0].setPosition([0.0,1.5,0.0])
		rand[0].setEuler([0.0,90.0,180.0])
		rand[0].group.grounded = True
		for m in rand[1:]:
			m.enable()
			self.snap(m, rand[0], add = False)
			print 'snapping ', m.name
		
		# Randomly enable some adjacent meshes
		keystone = random.sample(self._keystones, 1)[0]
		self._keystoneAdjacent.update({keystone:[]})
		for m in self.getAdjacent(keystone, self.getDisabled())[:4]:
			print m
			m.enable(animate = False)
		self.pickSnapPair()
		#snapGroup(smallBoneGroups)
		
	def pickSnapPair(self):
		self._quizTarget = random.sample(self._keystones, 1)[0]
		enabled = self.getEnabled(includeGrounded = False)
		if len(enabled) == 0:
			return
		self._quizSource = random.sample(self.getAdjacent(self._quizTarget, enabled)[:5],1)[0]
		self._quizPanel.setFields(self._quizSource.name, self._quizTarget.name)
		self.score.event(event = 'pickpair', description = 'Picked new pair of bones to snap', \
			source = self._quizSource.name, destination = self._quizTarget.name)
				
	def snap(self, sourceMesh, targetMesh, children = False, add = True):
		"""Overridden snap that supports adding more bones"""
		self.moveCheckers(sourceMesh)
		if children:
			sourceMesh.setGroupParent()
		sourceMesh.moveTo(targetMesh.checker.getMatrix(viz.ABS_GLOBAL))
		targetMesh.group.merge(sourceMesh)
		if sourceMesh.group.grounded:
			self._keystones.append(sourceMesh)
		if add:
			self.addMesh()
		
	def addMesh(self):
		"""Add more meshes"""
		disabled = self.getDisabled()
		if len(disabled) == 0:
			return
		keystone = random.sample(self._keystones, 1)[0]
		try:
			m = self.getAdjacent(keystone, disabled)[random.randint(0,3)]
		except (ValueError, IndexError):
			m = self.getAdjacent(keystone, disabled)[0]
		m.enable(animate = True)
	
	def getSnapSource(self):
		"""Define source object for snapcheck"""
		return self._quizSource
	
	def getSnapTarget(self):
		"""Define target object for snapcheck"""
		return self._quizTarget
		
	def getSnapSearch(self):
		"""Define list of objects to search for snapcheck"""
		return [self._quizTarget]
		
class PinDrop():
	"""
	The complementary of the puzzle assembly test mode, where the task is to annotate an assembled
	model instead of assemble a model from prompted annotations
	"""
	def __init__(self):
		super(PinDrop, self).__init__()
		self.modeName = 'pindrop'
		
		self._dropTarget = None
		self._dropAttempts = 0
		
		self.implode()
		
	def pickLabelTarget(self):
		unlabeled = [m for m in self._meshes if not m.labeled]
		self._dropTarget = random.sample(unlabeled, 1)[0]
	
	def pinCheck(self):
		if self._dropAttempts >= 3:
			pass
	
	def bindKeys(self):
		self._keyBindings.append(vizact.onkeydown('o', model.proxManager.setDebug, viz.TOGGLE)) #debug shapes
		self._keyBindings.append(vizact.onkeydown(viz.KEY_ALT_R, self.pinCheck))
		self._keyBindings.append(vizact.onkeydown(viz.KEY_ALT_L, self.pinCheck))
		self._keyBindings.append(vizact.onkeydown('65460', self.viewcube.toggleModes)) # Numpad '4' key
	

class PuzzleScore():
	"""Handles scoring for the puzzle game"""
	def __init__(self, modeName):
		"""Init score datastructure, open up csv file"""
		self.startTime = datetime.datetime.now()
		self.scoreFile = open('.\\log\\'+ modeName + '\\' + self.startTime.strftime('%m%d%Y_%H%M%S') + '.csv', 'wb')
		self.csv = csv.writer(self.scoreFile)
		
		# Starting score
		self.score = 100
		
		self.header = ['timestamp','event name','description','source','destination']
		self.events = []
		
		self.csv.writerow(self.header)
		
#		self.textbox = viz.addTextbox()
#		self.textbox.setPosition(0.8,0.1)
#		self.textbox.message('Score: ' + str(self.score))
	
	def event(self, event = None, description = None, source = None, destination = None):
		"""Record an event in the score history"""
		print 'Score event!'
		currentEvent = dict(zip(self.header,[time.clock(), event, description, source, destination]))
		self.events.append(currentEvent)
		self.csv.writerow([self.events[-1][column] for column in self.header])
		
		self.update(self.events)
		
	def update(self, events):
		"""Iterative score calculation"""
		curEvent = events[-1]
		
		if curEvent['event name'] == 'snap' or curEvent['event name'] == 'autosnap':
			scoreWeights = [10, 5, 2, 0] # 10pt for first attempt, 5 for second attempt, etc...
			snapCount = 0
			i = -2

			while True: # How many snaps did it take?
				if events[i] == 'snap' or events[i] == 'autosnap':
					self.score += scoreWeights[snapCount]
					break
				if events[i] == 'snapfail':
					snapCount += 1
				if -i > len(events) - 1:
					break
				i -= 1
				
		print self.score
#		self.textbox.message('Score: ' + str(self.score))

	def close(self):
		"""
		Close CSV file
		"""
		self.csv.close()

def end():
	"""Do everything that needs to be done to end the puzzle game"""
	print "Puzzle Quitting!"
	global controlInst
	if controlInst:
		controlInst.end()
#	except AttributeError:
#		print 'Not initialized'
#	del(controlInst)

def start(mode, dataset):
	"""Start running the puzzle game"""
	global controlInst
	global menuMode
	
	menuMode = mode
	
	if mode == 'Free Play':
		controlInst = FreePlay()
	elif mode == 'Quiz Mode':
		controlInst = TestPlay()
	try:
		controlInst.load(dataset)
	except KeyError:
		print "Dataset does not exist!"
		raise

def csvToList(location):
	"""Read in a CSV file to a list of lists"""
	raw = []
	try:
		with open(location, 'rb') as csvfile:
			wowSuchCSV = csv.reader(csvfile, delimiter=',')
			for row in wowSuchCSV:
				raw.append(row)
	except IOError:
		print "ERROR: Unable to open CSV file at", location
	return raw


def soundTask(pointer):
	"""
	Function to be placed in Vizard's task scheduler
		looks through proximity list and searches for the closest bone to the glove and puts it at
		the beginning of the list, allows the bone name and bone description to be played
	"""
#	while True:
#		yield viztask.waitTime(0.25)
#		if(len(proximityList) >0):
#			bonePos = proximityList[0].getPosition(viz.ABS_GLOBAL)
#			pointerPos = pointer.getPosition(viz.ABS_GLOBAL)
#			shortestDist = vizmat.Distance(bonePos, pointerPos)
#			
#			for i,x in enumerate(proximityList):
#				proximityList[i].incProxCounter()  #increase count for how long glove is near bone
#				bonePos = proximityList[i].getPosition(viz.ABS_GLOBAL)
#				pointerPos = pointer.getPosition(viz.ABS_GLOBAL)
#				tempDist = vizmat.Distance(bonePos,pointerPos)
#				#displayBoneInfo(proximityList[0])
#
#				if(tempDist < shortestDist):
##					removeBoneInfo(proximityList[0])
#					shortestDist = tempDist
#					tempBone = proximityList[i]
#					proximityList[i] = proximityList[0]
#					proximityList[0] = tempBone
#			#tempBone = proximityList[0]
#			displayBoneInfo(proximityList[0])
#			
#			if proximityList[0].proxCounter > 2 and proximityList[0].getNameAudioFlag() == 1:
#				#yield viztask.waitTime(3.0)
#				vizact.ontimer2(0,0,playName,proximityList[0])
#				proximityList[0].clearProxCounter()
#				proximityList[0].setNameAudioFlag(0)
#			if tempBone.proxCounter > 2 and tempBone.getDescAudioFlag() == 1:
#				yield viztask.waitTime(1.5)
#				#playBoneDesc(proximityList[0])
#				vizact.ontimer2(0,0, playBoneDesc,tempBone)
#				tempBone.setDescAudioFlag(0)	

def playName(boneObj):
	"""Play audio with the same name as the bone"""
	try:
		viz.playSound(path + "audio_names\\" + boneObj.name + ".wav") # should be updated to path
	except ValueError:
		print ("the name of the audio name file was wrong")
		
def planeProj(planePoint, planeNormal, targetPoint):
	"""
	Take in plane given by equation ax+by+cz+d=0 in the format [a, b, c, d] and
	compute projected distance from point
	"""
	planeToTarget = numpy.subtract(targetPoint, planePoint)
	return numpy.dot(planeNormal, planeToTarget)
