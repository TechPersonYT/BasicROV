import pygame
import threading
import numpy as np
import time
import socket
import random
import zlib
import imutils
import cv2

WIDTH, HEIGHT = (640, 480)
RESOLUTION = (WIDTH, HEIGHT)
CENTER = (round(WIDTH/2), round(HEIGHT/2))
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
DEADZONE = 0.8 # Absolute deadzone for joystick analog --> digital conversion (obsolete)

#HOST, PORT = ("169.254.38.171", 12345)
HOST, PORT = ("192.168.2.50", 12345)

image_clock = pygame.time.Clock()

pygame.init()
d = pygame.display.set_mode(RESOLUTION)

font = pygame.font.SysFont("ROVfont", 25)

temp = None

mouse_pos_current = (0, 0)

frame_cache_limit = 60*60 # (About) one minute of cache (this might be a memory hog depending on the image quality set on the Raspbery Pi. Turn the second multiplied value down if it's too high)
frame_cache = [np.zeros((480, 640, 3), np.uint8)]*frame_cache_limit # Contains up to frame_cache_limit previous frames, initialize with blank frames
frame_index = frame_cache_limit
opencv_contour_accuracy = 0.04
live_calculate = False
raspi_connected = False
snap_index = 0
raspi_image = None
raspi_camera_connected = False
gui_hidden = False
saving_image = False # Saving Snapshot
deleting_image = False # Deleting current Snapshot
showing_image = False # Showing Snapshot
snapshot = [] # List of snapshots
opencv_active = True # Whether or not we use OpenCV integration
snapshot_calculated = False # Whether or not we've run OpenCV on our snapshot since it was taken
showing_extrainfo = False # Whether or not we show the corresponding shape to each location in the OpenCV detection

def blit_shape_ref_image(x, y):
    global d
    # 20, 120
    pygame.draw.polygon(d, WHITE, [(10+x, 10+y),
                                             (0+x, 26+y),
                                             (20+x, 26+y)])
    pygame.draw.circle(d, WHITE, (10+x, 47+y), 10)
    square = pygame.Rect(0+x, 67+y, 20, 20)
    pygame.draw.rect(d, WHITE, square)
    pygame.draw.line(d, WHITE, (0+x, 100+y), (20+x, 120+y), 3)

mouse_pos1 = [] # Two left mouse click positions
mouse_pos2 = [] # Two right mouse click positions
mouse_pos1_distance = None # Distance between positions
mouse_pos2_distance = None # Distance between positions

num_rects = 0
num_circles = 0
num_lines = 0
num_squares = 0
num_triangles = 0

status = [] # Current tasks being done by thread functions
extra_messages = [] # Extra info messages to be blitted last

def blit_alpha(target, source, location, opacity):
        x = location[0]
        y = location[1]
        temp = pygame.Surface((source.get_width(), source.get_height())).convert()
        temp.blit(target, (-x, -y))
        temp.blit(source, (0, 0))
        temp.set_alpha(opacity)        
        target.blit(temp, location)

def translate(value, leftMin, leftMax, rightMin, rightMax): # Borrowed from stackoverflow
    # Figure out how 'wide' each range is
    leftSpan = leftMax - leftMin
    rightSpan = rightMax - rightMin

    # Convert the left range into a 0-1 range (float)
    try:
        valueScaled = float(value - leftMin) / float(leftSpan)
    except ZeroDivisionError:
        valueScaled = 0

    # Convert the 0-1 range into a value in the right range.
    newValue = rightMin + (valueScaled * rightSpan)
    if newValue > rightMax:
        newValue = rightMax
    if newValue < rightMin:
        newValue = rightMin
    return newValue

def detect(contour):
        global num_rects, num_circles, num_lines, num_squares, num_triangles, opencv_contour_accuracy
        # initialize the shape name and approximate the contour
        shape = "unidentified"
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, opencv_contour_accuracy * peri, True)

	# if the shape is a triangle, it will have 3 vertices
        if len(approx) == 3:
            shape = "triangle"
            num_triangles += 1
        # if the shape has 4 vertices, it is either a square or
        # a rectangle
        elif len(approx) == 4:
                # compute the bounding box of the contour and use the
		# bounding box to compute the aspect ratio
                (x, y, w, h) = cv2.boundingRect(approx)
                ar = w / float(h)

		# a square will have an aspect ratio that is approximately
                # equal to one, otherwise, the shape is a rectangle
                if ar >= 0.95 and ar <= 1.05:
                    shape = "square"
                    num_squares += 1
                else:
                    shape = "line"
                    num_lines += 1
		#shape = "square" if ar >= 0.95 and ar <= 1.05 else "line"
        elif len(approx) > 4:
            shape = "circle"

        # return the name of the shape
        return shape, approx

def detect_contours_from_image(image):
    global num_rects, num_circles, num_lines, num_squares, num_triangles, showing_extrainfo

    num_rects = 0
    num_circles = 0
    num_lines = 0
    num_squares = 0
    num_triangles = 0
    
    resized = imutils.resize(image, width=300)
    ratio = image.shape[0] / float(resized.shape[0])

    # convert the resized image to grayscale, blur it slightly,
    # and threshold it
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.threshold(blurred, 60, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.bitwise_not(thresh)

    # find contours in the thresholded image and initialize the
    # shape detector
    contours = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = imutils.grab_contours(contours)

    i = -1

    # loop over the contours
    for contour in contours:
        i += 1
        # compute the center of the contour, then detect the name of the
        # shape using only the contour
        M = cv2.moments(contour)
        try:
            cX = int((M["m10"] / M["m00"]) * ratio)
        except ZeroDivisionError:
            continue
        try:
            cY = int((M["m01"] / M["m00"]) * ratio)
        except ZeroDivisionError:
            continue
        shape, approx = detect(contour)
        # multiply the contour (x, y)-coordinates by the resize ratio,
        # then draw the contours and the name of the shape on the image
        contour = contour.astype("float")
        contour *= ratio
        contour = contour.astype("int")
        color_ratio = int(translate(i, 0, len(contours)-1, 0, 255))
        cv2.drawContours(image, [contour], -1, (color_ratio, 255-color_ratio, color_ratio), 2)
        if showing_extrainfo:
            cv2.putText(image, shape+" (Detected Points: "+str(len(approx))+")", (cX, cY), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 2)
    return image

# For pygame image use the following with numpy imported as np: image = pygame.surfarray.make_surface(np.rot90(cv2.cvtColor(raspi_image, cv2.COLOR_BGR2RGB)))

def status_display():
    global status, temp, num_lines, num_circles, shape_ref_image, num_squares, num_rects, num_triangles, DEADZONE, mouse_pos_current, live_calculate, raspi_camera, raspi_camera_connected, raspi_image, d, saving_image, snapshot, showing_image, gui_hidden, snap_index, deleting_image, mouse_pos1_distance, mouse_pos2_distance, opencv_active, snapshot_calculated, raspi_image_edited, mouse_pos1, mouse_pos2, frame_cache, frame_index
    clock = pygame.time.Clock()
    while True:
        status.append("drawing")
        d.fill(BLACK)
        if type(raspi_image) != type(None) and not showing_image:
            if showing_image == False:
                if live_calculate == False or opencv_active == False:
                    if frame_index >= len(frame_cache):
                        d.blit(pygame.surfarray.make_surface(np.rot90(cv2.cvtColor(raspi_image, cv2.COLOR_BGR2RGB))), (0, 0))
                    else:
                        d.blit(pygame.surfarray.make_surface(np.rot90(cv2.cvtColor(frame_cache[frame_index], cv2.COLOR_BGR2RGB))), (0, 0))
                elif live_calculate == True and opencv_active == True:
                    raspi_image_cv = detect_contours_from_image(raspi_image.copy()) # Detect shapes
                    raspi_image_edited = pygame.surfarray.make_surface(np.rot90(cv2.cvtColor(raspi_image_cv, cv2.COLOR_BGR2RGB))) # Convert back into pygame image
                    #raspi_image_edited = pygame.transform.flip(raspi_image_edited, True, False)
                    d.blit(raspi_image_edited, (0, 0)) # Blit
        elif showing_image:
            if snapshot != []: # We have a snapshot
                if not opencv_active:
                    d.blit(snapshot[snap_index], (0, 0))
                elif opencv_active and not snapshot_calculated:
                    raspi_image_cv = detect_contours_from_image(snapshot[snap_index].copy()) # Detect shapes
                    raspi_image_edited = pygame.surfarray.make_surface(np.rot90(cv2.cvtColor(raspi_image_cv, cv2.COLOR_BGR2RGB))) # Convert back into pygame image
                    #raspi_image_edited = pygame.transform.flip(raspi_image_edited, True, False)
                    d.blit(raspi_image_edited, (0, 0)) # Blit
                    snapshot_calculated = True
                elif snapshot_calculated:
                    d.blit(raspi_image_edited, (0, 0))
        if saving_image:
            if frame_index >= frame_cache_limit:
                snapshot.append(raspi_image.copy())
            else:
                snapshot.append(frame_cache[frame_index].copy())
            saving_image = False
            snapshot_calculated = False
        if deleting_image:
            if snapshot != []:
                try:
                    snapshot.remove(snapshot[snap_index])
                    if snap_index > len(snapshot)-1:
                        snap_index = len(snapshot)-1
                except (IndexError, ValueError):
                    pass
            deleting_image = False
            snapshot_calculated = False
        string = ""
        for process in status:
            if process != "drawing": # No need to show that we're showing whether we're showing anything or not
                if status.index(process) != 0:
                    string += ", "+process
                elif status.index(process) == 0:
                    string += process
        if len(status) < 2: # We're the only process; nothing else is running
            string = "Nothing"
        if gui_hidden == False:
            try:
                text0 = font.render("Display FPS: "+str(round(clock.get_fps(), 1)), True, WHITE)
                d.blit(text0, (0, 0))
                text1 = font.render("Image FPS: "+str(round(image_clock.get_fps(), 1)), True, WHITE)
                d.blit(text1, (0, 20))
                text = font.render("Running: "+string, True, WHITE)
                d.blit(text, (0, 40))
                if temp != None:
                    #print(round(translate(temp, 40, 90, 255, 10)))
                    text2 = font.render("Temperature: "+str(round(temp, 2)), True, (round(translate(temp, 60, 90, 0, 255)), 255-round(translate(temp, 60, 90, 0, 255)), 255-round(translate(temp, 60, 90, 0, 255))))
                elif temp == None:
                    text2 = font.render("Temperature Offline", True, WHITE)
                d.blit(text2, (0, 60))
                text3 = font.render("Deadzone (Use X and Y to adjust): "+str(round(DEADZONE, 1)), True, WHITE)
                d.blit(text3, (0, 80))
                if showing_image:
                    text4 = font.render("Viewing snapshot "+str(snap_index+1)+"/"+str(len(snapshot))+" (Use A to save image and B to view)", True, WHITE)
                elif not frame_index >= len(frame_cache):
                    text4 = font.render("Viewing frame "+str(frame_index)+"/"+str(frame_cache_limit)+" (Use A to save image and B to view)", True, WHITE)
                elif not showing_image:
                    text4 = font.render("Viewing live (Use A to save image and B to view)", True, WHITE)
                d.blit(text4, (0, 100))
                text5 = font.render(str(num_triangles), True, RED)
                d.blit(text5, (0, 130))
                text6 = font.render(str(num_circles), True, RED)
                d.blit(text6, (0, 160))
                text7 = font.render(str(num_squares), True, RED)
                d.blit(text7, (0, 190))
                text8 = font.render(str(num_lines), True, RED)
                d.blit(text8, (0, 220))
                blit_shape_ref_image(max(text5.get_width(), text6.get_width(), text7.get_width(), text8.get_width())+5, 120)
                #blit_alpha(d, shape_ref_image, (max(text5.get_width(), text6.get_width(), text7.get_width(), text8.get_width())+5, 120), 255)
                i = 220 # Current pixel offset
                for message in extra_messages:
                    i += 20 # Add to pixel offset
                    text, color = message
                    d.blit(font.render(text, True, color), (0, i))
                if mouse_pos1_distance != None:
                    i += 20
                    text = font.render("Pixel distance between point set 1: "+str(round(mouse_pos1_distance, 2)), True, WHITE)
                    d.blit(text, (0, i))
                if mouse_pos2_distance != None:
                    i += 20
                    text = font.render("Pixel distance between point set 2: "+str(round(mouse_pos2_distance, 2)), True, WHITE)
                    d.blit(text, (0, i))
                if len(mouse_pos1) == 2:
                    pygame.draw.line(d, GREEN, mouse_pos1[0], mouse_pos1[1])
                elif len(mouse_pos1) == 1:
                    pygame.draw.line(d, GREEN, mouse_pos1[0], mouse_pos_current)
                if len(mouse_pos2) == 2:
                    pygame.draw.line(d, RED, mouse_pos2[0], mouse_pos2[1])
                elif len(mouse_pos2) == 1:
                    pygame.draw.line(d, RED, mouse_pos2[0], mouse_pos_current)
            except pygame.error:
                pass
        elif gui_hidden:
            try:
                    text = font.render("Gui hidden (Press G to show)", True, RED)
                    text.unlock()
                    d.blit(text, (0, 0))
            except pygame.error as msg:
                    print(msg)
        status.remove("drawing")
        if "resizing" not in status: # Can't flip while resizing
            pygame.display.flip()
        clock.tick()

def raspi_connect():
    global sock, raspi_connected, status, raspi
    status.append("raspi_connect")
    sock = socket.socket()
    try:
        sock.bind((HOST, PORT))
    except:
        print("Unable to connect to Raspberry Pi due to network issues. Please reconnect and try again.")
    sock.listen(5)
    raspi = list(sock.accept())[0]
    raspi_connected = True
    status.remove("raspi_connect")
def recvall(socket, amount):
    data = b''
    while len(data) < amount:
        packet = socket.recv(amount-len(data))
        if not packet:
            return none
        data += packet
    return data
def raspi_camera_connect():
    global sock2, raspi_camera_connected, status, raspi_camera, image_size, d, raspi_image, image_clock, frame_cache, frame_cache_limit, frame_index
    status.append("raspi_camera_connect")
    sock2 = socket.socket(socket.SOCK_DGRAM)
    sock2.bind((HOST, PORT+1))
    sock2.listen(5)
    raspi_camera = list(sock2.accept())[0]
    raspi_camera_connected = True
    status.remove("raspi_camera_connect")
    status.append("raspi_get_image")
    while True:
        buffersize = int(raspi_camera.recv(1024).decode())
        #print(image_size)
        #print(buffersize)
        raspi_camera.sendall(".".encode()) # Raspi can't wait forever twice!
        #print("Uncompressing...")
        #print("Done")
        #print("Beginning of image: "+str(str(buffer_surf)[0:12]))
        #print("End of image: "+str(str(buffer_surf)[len(buffer_surf)-11:len(buffer_surf)-1]))
        #print("Length of image: "+str(buffersize))
        #raspi_image = pygame.image.fromstring(buffer_surf, image_size, "RGB")
        status.append("image_lock")
        try:
            encoded_image = np.fromstring(raspi_camera.recv(buffersize), np.uint8)
            raspi_image = cv2.imdecode(encoded_image, cv2.IMREAD_COLOR)
            frame_cache.append(raspi_image.copy())
            if len(frame_cache) > frame_cache_limit:
                frame_cache.remove(frame_cache[0]) # Remove the first item if the frame cache is full
            if frame_index > 0 and frame_index < frame_cache_limit: # Only hold this frame if we're scrolling through them
                frame_index -= 1 # Stay on current actual frame as long as possible (everything is shifted downward each frame)
        except BaseException as error:
            print(error)
        status.remove("image_lock")
        image_clock.tick()

joystick_connected = False

def joystick_connect():
    global joystick_connected, status
    status.append("joystick_connect")
    try:
        joystick = pygame.joystick.Joystick(0)
        joystick_connected = True
        joystick.init()
    except:
        text = font.render("No joystick detected!", True, RED)
        c = list(CENTER)
        d.blit(text, (c[0]-round(text.get_width()/2), c[1]-round(text.get_width()/2)))
    status.remove("joystick_connect")

def communicate():
    global temp, raspi_connected, raspi, left, right
    while True:
        if raspi_connected:
            raspi.sendall(str((left, right)).encode())
            temp = eval(raspi.recv(1024))

def clip(value, minimum, maximum):
    if value > maximum:
        value = maximum
    if value < minimum:
        value = minimum
    return value

left = 0.0
right = 0.0

# Use joystick axes 1 and 3

def eventloop():
    global joystick, status, showing_extrainfo, live_calculate, temp, mouse_pos_current, opencv_contour_accuracy, DEADZONE, left, right, saving_image, showing_image, gui_hidden, snap_index, deleting_image, mouse_pos1, mouse_pos2, mouse_pos1_distance, mouse_pos2_distance, opencv_active, snapshot_calculated, frame_index
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                exit()
            elif event.type == pygame.MOUSEMOTION:
                mouse_pos_current = event.pos
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: # Left click
                    if len(mouse_pos1) >= 2: # Reset positions in this list
                        mouse_pos1 = [pygame.Vector2(event.pos)]
                    elif len(mouse_pos1) < 2:
                        mouse_pos1.append(pygame.Vector2(event.pos))
                    if len(mouse_pos1) == 2: # Calculate distance
                        mouse_pos1_distance = abs(mouse_pos1[0].distance_to(mouse_pos1[1]))
                if event.button == 2: # Middle click
                    mouse_pos1 = [] # Clear all positions
                    mouse_pos2 = []
                if event.button == 3: # Right click
                    if len(mouse_pos2) >= 2: # Reset positions in this list
                        mouse_pos2 = [pygame.Vector2(event.pos)]
                    elif len(mouse_pos2) < 2:
                        mouse_pos2.append(pygame.Vector2(event.pos))
                    if len(mouse_pos2) == 2: # Calculate distance
                        mouse_pos2_distance = abs(mouse_pos2[0].distance_to(mouse_pos2[1]))
                if event.button == 5: # Mouse scroll up
                    if pygame.key.get_mods() == 1: # Shift (Increments of 5)
                        if frame_index-5 >= 0:
                            frame_index -= 5
                        else:
                            frame_index = 0
                    elif pygame.key.get_mods() == 64: # Ctrl (Increments of 1)
                        if frame_index-1 >= 0:
                            frame_index -= 1
                        else:
                            frame_index = 0
                    elif pygame.key.get_mods() == 0: # None (Increments of 15)
                        if frame_index-15 >= 0:
                            frame_index -= 15
                        else:
                            frame_index = 0
                if event.button == 4: # Mouse scroll down
                    if pygame.key.get_mods() == 1: # Shift (Increments of 5)
                        if frame_index+5 <= frame_cache_limit:
                            frame_index += 5
                        else:
                            frame_index = frame_cache_limit
                    elif pygame.key.get_mods() == 64: # Ctrl (Increments of 1)
                        if frame_index+1 <= frame_cache_limit:
                            frame_index += 1
                        else:
                            frame_index = frame_cache_limit
                    elif pygame.key.get_mods() == 0: # None (Increments of 15)
                        if frame_index+15 <= frame_cache_limit:
                            frame_index += 15
                        else:
                            frame_index = frame_cache_limit
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_g:
                    gui_hidden = not gui_hidden # Toggle Gui
                elif event.key == pygame.K_a: # Save current image
                    saving_image = True
                elif event.key == pygame.K_b:
                    showing_image = not showing_image
                elif event.key == pygame.K_i: # Show or hide extra OpenCV information
                    showing_extrainfo = not showing_extrainfo
                    snapshot_calculated = False
                elif event.key == pygame.K_l:
                    live_calculate = not live_calculate
                elif event.key == pygame.K_x:
                    if DEADZONE > 0.2:
                        DEADZONE -= 0.1
                elif event.key == pygame.K_y:
                    if DEADZONE < 0.9:
                        DEADZONE += 0.1
                elif event.key == pygame.K_LEFT:
                    if snap_index >= 1:
                        snap_index -= 1
                        snapshot_calculated = False
                elif event.key == pygame.K_RIGHT:
                    if snap_index < len(snapshot)-1:
                        snap_index += 1
                        snapshot_calculated = False
                elif event.key == pygame.K_UP: # Increase OpenCV detection "accuracy" value
                    opencv_contour_accuracy += 0.02
                elif event.key == pygame.K_DOWN: # Decrease OpenCV detection "accuracy" value
                    if opencv_contour_accuracy > 0.02:
                        opencv_contour_accuracy -= 0.02
                elif event.key == pygame.K_SPACE: # Force recalculate OpenCV detection for current image
                        snapshot_calculated = False
                elif event.key == pygame.K_BACKSPACE: # Delete current image that is being viewed
                    if showing_image:
                        deleting_image = True
                        snapshot_calculated = False
                elif event.key == pygame.K_c: # Toggle OpenCV detection
                    opencv_active = not opencv_active
                    if opencv_active:
                            snapshot_calculated = False
            elif event.type == pygame.JOYAXISMOTION:
                if event.axis == 1: # Left Y axis
                    if event.value > DEADZONE:
                        left = clip(event.value, -1.0, 1.0)
                    elif event.value < -DEADZONE:
                        left = clip(event.value, -1.0, 1.0)
                    else:
                        left = 0.0
                elif event.axis == 3: # Right Y axis
                    if event.value > DEADZONE:
                        right = clip(event.value, -1.0, 1.0)
                    elif event.value < -DEADZONE:
                        right = clip(event.value, -1.0, 1.0)
                    else:
                        right = 0.0
            elif event.type == pygame.JOYBUTTONDOWN:
                if event.button == 0:
                    print("A")
                    saving_image = True
                elif event.button == 1:
                    print("B")
                    showing_image = not showing_image
                elif event.button == 2:
                    print("X")
                    if DEADZONE > 0.2:
                        DEADZONE -= 0.1
                elif event.button == 3:
                    print("Y")
                    if DEADZONE < 0.9:
                        DEADZONE += 0.1

# Introduction and keybindings print out for people who don't use this program often
print("Welcome to ROV_gui 3. This is a program designed for the MATE Robotics competition intended to be used alongside a Raspberry Pi running client.py and camera.py.")
print("Keybindings:")
print("    G: Show/Hide gui. Does not show or hide OpenCV detection results.")
print("    C: Enable/Disable OpenCV contour approximation for shape detection.")
print("    Up: Increase OpenCV approxPolyDP accuracy value.")
print("    Down: Decrease OpenCV approxPolyDP accuracy value.")
print("    Left: Show previous snapshot.")
print("    Right: Show subsequent snapshot.")
print("    Backspace: Delete current snapshot.")
print("    Space: Manually recalculate OpenCV detection for current view.")
print("    A: Save the currently viewed image as a snapshot.")
print("    B: Show/Hide snapshot view.")
print("    X: Decrease joystick deadzone range.")
print("    Y: Increase joystick deadzone range.")
print("    I: Show extra OpenCV information, including the corresponding name for each highlighted shape.")
print("    Left Joystick Y Axis: Control the left Mini ROV motor.")
print("    Right Joystick Y Axis: Control the right Mini ROV motor.")
print("    Mouse Left Click: Set a starting or ending point for line distance measurement.")
print("    Mouse Right Click: Set a starting or ending point for line distance measurement.")
print("    Mouse Middle Click: Clear all starting and ending points for line distance measurements.")
print("A, B, X, and Y buttons can be pressed on either a keyboard or a joystick.")
print("Viewing a snapshot, changing the currently viewed snapshot by using the arrow keys or deleting a snapshot, and enabling OpenCV will initialize a recalculate of the contours.")

t1 = threading.Thread(target=status_display)
t2 = threading.Thread(target=raspi_connect)
t3 = threading.Thread(target=joystick_connect)
#t4 = threading.Thread(target=eventloop)
t5 = threading.Thread(target=communicate)
t6 = threading.Thread(target=raspi_camera_connect)

t1.start()
t2.start()
t3.start()
#t4.start()
t5.start()
t6.start()

eventloop()
