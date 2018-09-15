import socket
import sys

HOST, PORT = ("SOME_IP_ADDRESS", 5431) # Set this to your intended IP address and port

tried = False

def translate(value, leftMin, leftMax, rightMin, rightMax): # Borrowed from stackoverflow
    # Figure out how 'wide' each range is
    leftSpan = leftMax - leftMin
    rightSpan = rightMax - rightMin

    # Convert the left range into a 0-1 range (float)
    valueScaled = float(value - leftMin) / float(leftSpan)

    # Convert the 0-1 range into a value in the right range.
    return rightMin + (valueScaled * rightSpan)

try:
    import pygame
except ModuleNotFoundError:
    answer = input("Pygame not found. Attempt to install? (yes or no)")
    if "y" in answer.lower():
        import subprocess as sub
        print(sub.getoutput("pip3 install pygame"))
        tried = True
if tried:
    try:
        import pygame
    except ModuleNotFoundError:
        print("Pygame installation failed. Quitting... (Is pip installed?)")
        sys.exit(1)

sock = socket.socket(socket.SO_REUSEADDR)
sock.bind((HOST, PORT))
sock.listen(1)
print("Waiting for client...")
raspi, address = sock.accept()

# CLIENT SIDE
# sock = socket.socket()
# sock.connect((HOST, PORT))
# sockfile = sock.makefile(mode="r")

pygame.init()

d = pygame.display.set_mode((640, 480), pygame.DOUBLEBUF) # Display initialization. Window size might need tweaking.

fallback = False # Flag to determine whether to use keyboard input instead of joystick

if pygame.joystick.get_count() > 0:
    current_joy = pygame.joystick.Joystick(0)
    current_joy.init()
    print("Initializing joystick "+current_joy.get_name())
else:
    print("Warning! No joystick detected. Falling back to keyboard+mouse.")
    fallback = True

font = pygame.font.SysFont("customFont1", 20, True) # TODO: Adjust text size to match window size (or vise versa) to prevent overscan

axes = []

def wait_joyzero(axis, deadzone=0.3):
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.JOYAXISMOTION:
                if event.axis == axis and abs(event.value) < deadzone:
                    waiting = False
def joystick_debug(): # This is kind of deprecated. It is recommended to use calibrate() instead.
    global current_joy, axes
    fallback = False # Lazy code. Some stuff was deprecated and this is the result.
    debugging = True # More lazy code.
    if fallback is False:
        while debugging:
            d.fill((0, 0, 0))
            for axis in range(0, current_joy.get_numaxes()): # Update code for debugging
                axes[axis] = [current_joy.get_axis(axis), axis]
            for axis_value in axes:
                surf = font.render("Axis "+str(round(axis_value[1], 3))+" = "+str(round(axis_value[0], 3)))
                d.blit(surf, (0, axis_value[1]*(surf.get_height()*1.2))) # Use 2/10 of the height of the surface as spacing between the surfaces
            d.flip()

def calibrate():
    global joymap, current_joy, axes
    joymap = {"motorright":[0, 0], "motorleft":[0, 0], "motorup":[0, 0]} # {map1} = {[axis, reversed]}
    calibrating = True
    d.fill((0, 0, 0))
    surf = font.render("Use left motor joystick.", True, (0, 255, 0)) # Left motor joystick calibration
    d.blit(surf, (round(d.get_width()/2)-(surf.get_width()/2), round(d.get_height()/2)-(surf.get_width()/2)))
    pygame.display.flip()
    while calibrating:
        for event in pygame.event.get():
            if event.type == pygame.JOYAXISMOTION:
                if abs(event.value) > 0.9:
                    lastaxis = event.axis
                    if event.value < 0: # It's reversed.
                        joymap["motorleft"][0] = lastaxis
                        joymap["motorleft"][1] = True
                        calibrating = False
                    elif event.value > 0: # It's not reversed.
                        joymap["motorleft"][0] = lastaxis
                        joymap["motorleft"][1] = False
                        calibrating = False
    d.fill((0, 0, 0))
    surf = font.render("Use right motor joystick.", True, (0, 255, 0)) # Right motor joystick calibration
    d.blit(surf, (round(d.get_width()/2)-(surf.get_width()/2), round(d.get_height()/2)-(surf.get_height()/2)))
    pygame.display.flip()
    wait_joyzero(lastaxis)
    calibrating = True
    while calibrating:
        for event in pygame.event.get():
            if event.type == pygame.JOYAXISMOTION:
                if abs(event.value) > 0.9:
                    lastaxis = event.axis
                    if event.value < 0: # It's reversed.
                        joymap["motorright"][0] = lastaxis
                        joymap["motorright"][1] = True
                        calibrating = False
                    elif event.value > 0: # It's not reversed.
                        joymap["motorright"][0] = lastaxis
                        joymap["motorright"][1] = False
                        calibrating = False
    d.fill((0, 0, 0))
    surf = font.render("Use up motor trigger.", True, (0, 255, 0)) # Up motor trigger calibration.
    d.blit(surf, (round(d.get_width()/2)-(surf.get_width()/2), round(d.get_height()/2)-(surf.get_width()/2)))
    pygame.display.flip()
    wait_joyzero(lastaxis)
    calibrating = True
    while calibrating:
        for event in pygame.event.get():
            #if event.type == pygame.JOYBUTTONDOWN:
            #        joymap["motorup"][0] = event.button
            #        joymap["motorup"][1] = False
            #        calibrating = False
            if event.type == pygame.JOYAXISMOTION:
                if abs(event.value) > 0.9:
                    lastaxis = event.axis
                    if event.value < 0: # It's reversed.
                        joymap["motorup"][0] = lastaxis
                        joymap["motorup"][1] = True
                        calibrating = False
                    elif event.value > 0: # It's not reversed.
                        joymap["motorup"][0] = lastaxis
                        joymap["motorup"][1] = False
                        calibrating = False
calibrate()
running = True # This should be False until we have the number of joysticks and know what their ids correspond to, as this will (try to) send signals to the Pi. If it's True before than, it's for debug purposes

tank_steering = True

clock = pygame.time.Clock()

while running:
    d.fill((0, 0, 0))
    blitsurf = font.render(str(round(clock.get_fps(), 2))+" FPS", True, (0, 255, 0))
    d.blit(blitsurf, (0, 0))
    clock.tick()
    for event in pygame.event.get(): # New update code. Should be more efficient than deprecated code
        if event.type is pygame.QUIT:
            pygame.quit()
            raspi.send(b"\nraise RuntimeError")
            sys.exit()
        elif event.type is pygame.JOYAXISMOTION and fallback is False:
            if tank_steering: # Somewhat stable tank steering
                try:
                    if event.axis is joymap["motorleft"][0]:
                        if joymap["motorleft"][1] == False: # Mapping is not reversed.
                            if event.value >= 0:
                                string = "\nmotorleft = "+str(translate(event.value, 0.0, 1.0, 0, -255))
                                raspi.send(string.encode())
                                string = "\nmotorright_reversed = False"
                                raspi.send(string.encode())
                            if event.value < 0:
                                string = "\nmotorleft = "+str(translate(event.value, 0.0, -1.0, 0, -255))
                                raspi.send(string.encode())
                                string = "\nmotorleft_reversed = True"
                                raspi.send(string.encode())
                        if joymap["motorleft"][1] == True: # Mapping is reversed (swap conditions. May have to swap False, True as well?)
                            if event.value < 0:
                                string = "\nmotorleft = "+str(translate(event.value, 0.0, 1.0, 0, -255))
                                raspi.send(string.encode())
                                string = "\nmotorright_reversed = False"
                                raspi.send(string.encode())
                            if event.value >= 0:
                                string = "\nmotorleft = "+str(translate(event.value, 0.0, -1.0, 0, -255))
                                raspi.send(string.encode())
                                string = "\nmotorleft_reversed = True"
                                raspi.send(string.encode())
                except Exception as msg:
                    print(msg)
                try:
                    if event.axis is joymap["motorright"][0]:
                        if joymap["motorright"][1] == True: # Mapping is not reversed
                            if event.value >= 0:
                                string = "\nmotorright = "+str(translate(event.value, 0.0, 1.0, 0, 255))
                                raspi.send(string.encode())
                                string = "\nmotorright_reversed = False"
                                raspi.send(string.encode())
                            if event.value < 0:
                                string = "\nmotorright = "+str(translate(event.value, 0.0, -1.0, 0, 255))
                                raspi.send(string.encode())
                                string = "\nmotorright_reversed = True"
                                raspi.send(string.encode())
                        if joymap["motorright"][1] == False: # Mapping is reversed (swap conditions. May have to swap False, True as well?)
                            if event.value < 0:
                                string = "\nmotorright = "+str(translate(event.value, 0.0, 1.0, 0, 255))
                                raspi.send(string.encode())
                                string = "\nmotorright_reversed = False"
                                raspi.send(string.encode())
                            if event.value >= 0:
                                string = "\nmotorright = "+str(translate(event.value, 0.0, -1.0, 0, 255))
                                raspi.send(string.encode())
                                string = "\nmotorright_reversed = True"
                                raspi.send(string.encode())
                except Exception as msg:
                    print(msg)
        elif event.type is pygame.KEYDOWN and fallback is True: # KEYDOWN
            if event.key is pygame.K_w:
                raspi.send(b"\nmotorleft = 1.0")
                raspi.send(b"\nmotorright = 1.0")
                raspi.send(b"\nmotorleft_reversed = False")
                raspi.send(b"\nmotorright_reversed = False")
            elif event.key is pygame.K_a:
                raspi.send(b"\nmotorright = 1.0")
                raspi.send(b"\nmotorleft = 1.0")
                raspi.send(b"\nmotorleft_reversed = True")
            elif event.key is pygame.K_s:
                raspi.send(b"\nmotorleft = 1.0")
                raspi.send(b"\nmotorright = 1.0")
                raspi.send(b"\nmotorleft_reversed = True")
                raspi.send(b"\nmotorright_reversed = True")
            elif event.key is pygame.K_d:
                raspi.send(b"\nmotorright = 1.0")
                raspi.send(b"\nmotorleft = 1.0")
                raspi.send(b"\nmotorleft_reversed = True")
        elif event.type is pygame.KEYUP and fallback is True: # KEYUP
            if event.key is pygame.K_w:
                raspi.send(b"\nmotorleft = 0.0")
                raspi.send(b"\nmotorright = 0.0")
                raspi.send(b"\nmotorleft_reversed = False")
                raspi.send(b"\nmotorright_reversed = False")
            elif event.key is pygame.K_a:
                raspi.send(b"\nmotorright = 0.0")
                raspi.send(b"\nmotorleft = 0.0")
                raspi.send(b"\nmotorleft_reversed = False")
            elif event.key is pygame.K_s:
                raspi.send(b"\nmotorleft = 0.0")
                raspi.send(b"\nmotorright = 0.0")
                raspi.send(b"\nmotorleft_reversed = False")
                raspi.send(b"\nmotorright_reversed = False")
            elif event.key is pygame.K_d:
                raspi.send(b"\nmotorright = 0.0")
                raspi.send(b"\nmotorleft = 0.0")
                raspi.send(b"\nmotorleft_reversed = False")
    raspi.send(b"\ni=0") # Just to keep it refreshing (as it will hang until a message is sent)
    pygame.display.flip()

                
    #for axis in range(0, current_joy.get_numaxes()): # Deprecated update code
    #    axes[axis] = [current_joy.get_axis(axis), axis]
    #tosend = "" # Basically a buffer so we're not sending one byte at a time # Deprecated
    #for axis_value in axes:
    #    tosend += str(axis_value[1])+" "+str(axis_value[0])+"\n"
    #    if debugging: # We might use this
            #surf = font.render("Axis "+str(round(axis_value[1], 3))+" = "+str(round(axis_value[0], 3)))
            #d.blit(surf, (0, axis_value[1]*(surf.get_height()*1.2))) # Use 2/10 of the height of the surface as spacing between the surfaces
    #sockfile.write(tosend)
    #if debugging:
    #    d.flip()

