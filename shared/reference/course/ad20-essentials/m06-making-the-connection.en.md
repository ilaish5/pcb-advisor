# AD20 Essentials - Module 6: Making the Connection

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 72-80 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.72 -->

## 6.1 Purpose

In this exercise, you will complete the Processor_Interface, CAN_Interface and
Digital_IO schematics by adding wires, net labels, power ports and ports to the design
for connecting the components.

## 6.2 Preparation

1. Close your current WCTopping.PrjPcB project.
2. Open the provided WCTopping.PrjPcb project from the
AD20 Essentials Exercises\ Module 6 - Making the Connection folder.

## 6.3 Wiring the Schematic

### 6.3.1 Shortcuts

Place » Wire (shortcut P » W)
Place » Power Port (shortcut P » O)
Place » Port (shortcut P » R)
Place » Net Label (shortcut P » N)

### 6.3.2 Processor_Interface Schematic

#### 6.3.2.1 Wire Connections

3. In your WCTopping.PrjPcb project, open the Processor_Interface.SchDoc. It
should only contain 3 components without any connections. By the end of this secti on,
this schematic will be populated with wires, port, power port and net label connections as
shown in Figure 79.
The negate overscore shown on ports CS   and IOexpand_  CS can be created
by entering a backslash “\” character after the character to negate.

<!-- p.73 -->

*Figure 79. Processor_Interface Schematic*
4. We will connect Pin 1 and Pin 17 of the header (J4). Use Figure 79 above as a reference.
a) Use Place » Wire (shortcut P » W).
b) Move the cursor near the tip of the Pin 1 of J4. You will see a cross appear, indicating
you are on the pin’s electrical hotspot as seen in Figure 80.
c) Left-click when the hotspot is active to begin placing a wire segment.
d) Press Spacebar to flip the bending side of wire if needed.
e) A new segment will start with each left-click until another electrical hotspot is clicked on
(such as another pin) to complete the placement of this first wire.
f) Complete the connection from Pin 1 to Pin 17
5. During placement of a segment, right-click once to stop the current segment but remain in
placement mode.
6. Connect Pin 9, Pin 25 and Pin 39 using the method described in Step 4.
7. Right-click twice (while there is no current wire being placed) to exit the command.
Cross-Overs may be displayed depending on the settings in your Schematic
Preferences; Section Schematic – General  and  the option Display Cross Overs

<!-- p.74 -->

*Figure 80. Electrical Hotspot of a pin for schematic connections*
Use Spacebar to change the angle of a wire corner during placement.
Use Shift+Spacebar to change the corner mode of a wire during placement.
Use Backspace to unwind an inadvertently placed segment during placement.
Use Right-click or Escape to end placement mode.

#### 6.3.2.2 Smart Paste Wires

8. Place a short wire on Pin 19 of the header.
9. Select the wire stub and copy it with Edit » Copy or CTRL+C.
10. Use Edit » Paste or CTRL+V to paste the wire stub on the remaining unconnected pins on
the left side of the connector.
11. Select Edit » Smart Paste to open the Smart Paste dialog. This can also be done using the
CTRL+Shift+V shortcut keys.
12. Smart Paste knows that a wire object has been copied. Copied objects are shown in the left-
most list box.
13. In this case, you will be pasting the Wires as Themselves, so make sure Themselves is
selected in the Choose Paste Action list box.
14. Check the Enable Paste Array option on the right side. Create 20 rows of wires by setting
Column to Count 1, the Rows to Count 20, with a row spacing of 100mil and pressing OK.
15. Place the 20 wire stubs attached to the pins of the header on the right side of the connector.

#### 6.3.2.3 Power Ports

16. Let’s place a Power Port from  Place » Power Port, or from the Active Bar    to place a
power port.
17. Press Tab to access the properties as shown in Figure 81.

<!-- p.75 -->

*Figure 81. Changing the Power Port style in its Properties*
18. Change the Net to GND and set the Style to Power Ground. Press Enter or click on the
Pause symbol    to dismiss the dialog and continue placement of the power port.
19. Place two GND Power Ports below the header (J4), using Figure 79 on a previous page as
a guide.
20. Using Figure 79 for reference, add wires from the GND Power Ports to your existing circuit.
21. Using Figure 79 for reference, repeat the above process to add, modify and connect the 3V3
and 5V Power Ports above the header (J4). The power ports can be rotated by pressing
Spacebar while moving them. They can be changed to “Bar” type, by changing the “Style”
in the Properties panel.
22. Power ports may be placed directly on the pins of symbols. Place GND, 5V and 3V3 Power
Ports directly on the capacitors in the upper right corner of the
Processor_Interface.SchDoc schematic using Figure 79 as reference.
23. Using Figure 79 for reference, draw the remaining wires for the entire schematic. In the next
steps, we will describe how to place Net Labels and Ports.

#### 6.3.2.4 Net Labels

24. Right-click and select Place » Net Label or use the shortcuts P » N
25. With the Place Net Label command active, press Tab to open the Properties panel, so that
a name can be entered.
26. Enter the name GPIO2, press Enter and place the net label on the wire leading to pin 3 of
the header using Figure 79 for reference.
27. Continue to place all of the same Net Labels using Figure 79 for reference. Notice the
numeric values automatically incrementing. The properties of a Net Label can always be
changed by hitting TAB during placement, or double-clicking the Net Label and change its
name manually.

<!-- p.76 -->
Some Net Labels contain an Underscore that could be mistaken as a space, and not
clearly seen if placed on a Wire. These Net Labels include SPI_xx, ID_xx and
IO_RESET group of Net Labels. This naming syntax is necessary for proper net
connectivity.
28. Double-check and make sure all Wires and Net Labels are place as shown in Figure 79. We
will be placing the Ports in the next step.
Moving Net Labels after they are placed on wires can be difficult because movi ng the
net label drags the attached wire. Selecting the Net Labels, then going to Edit » Move
» Move Selection can be helpful when moving net labels. Also, if ‘Always Drag’ is
enabled in Preferences, you may use Ctrl+left mouse button to drag a net label off of
a wire.

#### 6.3.2.5 Ports

29. Use the Place » Port command to place a port that will connect wires to another sheet in the
design. This can also be done by using the P»R shortcut keys.
30. Press the Tab key with the port active and change the name of the port to SDA1. Set the I/O
Type to Bidirectional as shown in Figure 82. Press Enter or click on the Pause symbol
to dismiss the dialog and continue placement of the port.
31. Place the SDA1 Port near Pin 3 of the header as shown in Figure 79 on a previous page.
The port will require two left-clicks. The first left-click defines the left side of the port, and the
second left-click defines the right-side of the port and its length.

<!-- p.77 -->

*Figure 82. Port Properties dialog*
32. Continue to place the ports as shown in Figure 79 on the previous page. Ports named
SPI_MISO, INT1, INT2, and CAN_INT should be set as Input for I/O Type, and the rest
should be set as Output.
Ports will automatically show their I/O type direction (such as Input, Output) once its
snapped to a Wire. The best way to place them, is to set their I/O Type in the
Properties, then snap it to a Wire.
33. Save the schematic.

<!-- p.78 -->

### 6.3.3 CAN_Interface Schematic

#### 6.3.3.1 Net Labels

34. Open CAN_Interface.SchDoc from your Projects panel.
35. Place » Net Label and press Tab to set the name to CAN_RXD. Place the net label between
the two resistors attached to UC2-4 (Pin 4 of UC2) as shown in Figure 83 below.

*Figure 83. CAN_RXD Net Label placement for UC2*
36. Place another instance of the CAN_RXD on the wire attached to UC1-2 to create a
connection without needing to place a wire as shown in Figure 84 below.

*Figure 84. CAN_RXD Net Label placement for UC1*

#### 6.3.3.2 Smart Paste Ports

37. Select the SPI_SCLK, SPI_MOSI, and SPI_MOSIA net labels, choosing the first one
then holding Shift down to select the remaining.
38. Copy the net labels with CTRL+C.
39. Select the menu Edit » Smart Paste or use the shortcut keys CTRL+SHIFT+V.
40. Select Ports for the Paste As option.
41. Making sure Enable Paste Array is not checked, that Sort Order is set to By Location,
Signal Names is set to Keep and Port Width is set to Set Width To Widest.
42. Press OK.
43. Place the ports on the SPI_SCLK, SPI_MOSI and SPI_MOSIA wires as shown in Figure
85 below.
44. Ensure that the SPI_MOSIA Port is set to Output.
45. Add a CAN_RXD port and set it to an Input Port, and wire it to Pin 2 of UC1 as shown in
Figure 85 below.
46. Save the schematic.

<!-- p.79 -->

*Figure 85. Finalized section of the CAN_Interface schematic*

### 6.3.4 Digital_IO Schematic

#### 6.3.4.1 Auto-Generated Wires

47. Open Digital_IO.SchDoc from the Projects panel.
48. Select the IOS1 header.
49. Drag the IOS1 header over to UI1 so that pins of the IOS1 header bump up against Pins
21-28 of UI1 as shown in Figure 86 below. Do not overlap them by too much.

*Figure 86. Overlap pins for UI1 and IOS1*
50. Drag the IOS1 away from UI1 to create wire connections between the pins automatically as
shown in Figure 87 below.
If Always Drag is not enabled in Schematic Preferences, holding the CTRL key will
be required for automatically creating connections.

<!-- p.80 -->

*Figure 87. Auto-Generated wires when pulling IOS1 away from UI1*
51. Repeat the above steps to generate wires for the IOS2 header so that it connects to Pins
GPB0-GPB7 of UI1.
52. Save the Processor_Interface, CAN_Interface, and Digital_IO schematics to
complete your work.
