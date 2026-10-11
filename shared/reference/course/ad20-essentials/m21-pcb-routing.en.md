# AD20 Essentials - Module 21: PCB Routing

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 208-217 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.208 -->

## 21.1 Purpose

In this exercise, you will practice routing using various PCB routing modes. Within
each mode, routing options and tips will also be discovered.
Routing is essentially the process of making electrical connections through tracks and vias. Altium
Designer provides a series of powerful interactive routing tools. The main aspects of Interactive
Routing (Clearance, Width, Allowed Layers and Via Style) are driven and defined by your Design
Rules.

## 21.2 Preparation

1. Go to File » Open, and head to the Module 21 - PCB Routing folder of the AD 20
Essential Exercises folder, and open WCToppingRouting.PcbDoc

## 21.3 Shortcuts

Routing  Modes:
Interactive Routing (shortcut U»T or CTRL+W)
Interactive Differential Pair Routing (shortcut U»I)
Active Route (shortcut SHIFT+A)

During Routing:
Help (shortcut F1 (Online Help)
Shortcuts List ~ (US) or Shift+F1 (other regions)
Elbow Side (shortcut Space)
Corner Style (shortcut Shift+Space)
Routing mode (shortcut Shift+R)
Track Width (shortcut Shift+W or 3)
Via Size (shortcut Shift+V or 4)
Layer Change (shortcut CTRL+L or regular layer change method)
Remove Last Segment (shortcut BACKSPACE)

Unroute:
Unroute Board (shortcut U»U»A)
Unroute Net (shortcut U»U»N)

<!-- p.209 -->

## 21.4 PCB Routing

### 21.4.1 Setting Preferences

2. Before routing, it’s good to be aware of some of the preferences which can affect its
behavior.
a) Press O - T to open the Preferences dialog to the PCB Editor branch on the Interactive
Routing page.
b) Set the following options as follows:
- Automatically Terminate Routing: On
- Automatically Remove Loops: On
- Track Width Mode: Rule Preferred
- Via Size Mode: Rule Preferred
c) Click OK to apply and close the Preferences dialog. In the lower right corner, go to
Panels » View Configuration. In the Layers & Colors tab, hide the Mechanical Layers
by clicking on the “eye” icon . You can close this panel.

### 21.4.2 Quick Routing for Simple Nets

In this section, we’ll hold the Ctrl key and left-click to quickly complete simple, local routes.
3. Jump to component UI1 by hitting J » C and type UI1. Without moving your cursor’s
location, zoom into UI1.
4. To start the Interactive Router, press the U - T shortcut keys, select the Route » Interactive
Routing menu command or click the Interactive Routing button on the Active Bar  .
5. Hold the Ctrl key, then left-click on one of the pads, e.g. Pad 28 of UI1. If the route is
possible on the selected layer, it will be instantly routed.
6. Continue to hold the Ctrl key and try another net, e.g., UI-27, UI1-26, UI-25. Right-click
or hit the Escape key to exit the interactive routing command.

### 21.4.3 Interactive Routing Nets

7. Zoom into the area of the board toward the upper left portion of the PCB shown in Figure
263 below. We will now route the connections between components P1, RTERM1,
DioCAN1, CH1, CL1, and UC2 through the following procedure:

*Figure 263. Connection lines (known as a Ratsnest) between un-routed components*
a) Start the route command with Route » Interactive Routing (or U - T hotkeys)
b) The cursor will change to a command crosshair, indicating that you are in an interactive
command.

<!-- p.210 -->
c) Left-click on Pad 2 of P1 to begin the route. Move the mouse away from the pad to see
the tracks the Interactive Router is planning to place.
d) Move your mouse to Pad 1 of RTERM1 and left-click to terminate the route. Upon
terminating the route, we will still remain in the interactive routing mode and the editor is
ready for the next net to route, as indicated by the active command crosshair.
8. While still in active interactive routing mode, left-click on Pad 1 of P1.
a) Hit the ~ tilde (US)  or Shift+F1 for other regions key to access all the shortcuts and
commands while in this mode. Notice that 3 is the hotkey to cycle track-width source of
this route as shown in Figure 264.
b) Press Esc to escape the shortcuts menu.

*Figure 264. Next available option or shortcut from the Tilde menu*
c) Hit the 3 key to cycle through the different trace width values set in the Trace Width
design rule.
d) You can hit the Spacebar key to toggle the "elbow side" angle (Start/End toggle).
e) Hit Shift + R to cycle through the available Conflict Resolution modes.
f) Experiment with a few of the different routing modes, Walkaround, HugNPush, Push,
Ignore Obstacles and Stop at First Obstacle. The current routing resolution mode is
displayed in the Status Bar and the Heads-Up Display as shown in Figure 265.

*Figure 265. Conflict Resolution modes displayed in the HUD*

<!-- p.211 -->
You can control which Conflict Resolution Modes are available by changing the
preferences in the PCB Editor branch under the Interactive Routing Page and altering
the preferences in the Routing Conflict Resolution section or by pressing Tab during a
route.
9. Hit the Backspace key to remove the last placed vertex while still in the routing command.
10. During a route:
a) Right-click once (or press Esc) to exit current route placement.
b) Right-click again while no routing is active (or press Esc) to exit the Interactive Routing
command completely.

### 21.4.4 Vias

#### 21.4.4.1 Setting Via Sizes

To have multiple via sizes available during interactive routing, we’ll modify the Routing Via Style
Design Rule.
11. Open the RoutingVias design rule in Design » Rules, section Routing - Routing Via Style.
a) Modify the Via Diameter and Via Hole Size values as shown in Figure 266. Note that the
Maximum values are in the middle.
b) Click OK to accept changes and close the dialog.

*Figure 266. Changing the Routing Via Style design rule*

#### 21.4.4.2 Adding Vias

12. Start the interactive routing command by pressing U - T.
a) Move the cursor and click on Pad 13 of component UC1.
b) Start routing and hit the + key on the NumPad to drop a via and go to the next signal
layer as shown in Figure 267. If you do not have a NumPad, hit the ~ tilde key and click
next layer.

<!-- p.212 -->
c) Hit the 4 key to toggle through the three via sizes that you added in the design rule
earlier.
d) After pressing the L key, a via should be added as shown in Figure 267. Click the left
mouse button to place the via.
e) Continue finishing the route on the bottom layer. Once completed, hit ESC or right-click
to end the command

*Figure 267. Changing Via Size while routing*
The active layer will now be switched to the Bottom Layer, as shown on the current
layer tab below. New routes will start on this active layer, unless if starting the route
from a top-layer surface mount pad.

It is not necessary to memorize all the interactive routing options. Instead, hit the tilde
(~) key located below the Esc button or the F1 key to display all available options.
This key works to display all possible command options within the PCB and Schematic
Editors.

### 21.4.5 Multi-Trace Routing

To improve the routing efficiency for grouped signals, especially buses, you can use the
Interactive Multi-Routing command.
13. Find UC1 in the PCB document using the command Jump » Component (shortcut J - C).
14. Hold Shift and click on Pads 12, 13, 14 and 16 to select multiple pads as shown in Figure
268.

<!-- p.213 -->

*Figure 268. UC1 pads to be used for Multi-Trace routing*
15. Start the multi-route from these pads using the command Route » Interactive Multi-
Routing (U » M). The command crosshair will appear to indicate you are in an interactive
command.
a) Left-click either of the four pads to set the base track for the multi-route.
b) Press Tab to open the Properties panel. Change the Bus Spacing to 10mil by pressing
From Rule (10mil). Also, while in the Properties panel, in the Interactive Routing
Options, change the routing mode to “Walkaround Obstacles” mode. Hit the Pause
button to resume routing.
c) Move the cursor down towards J4, and you will see four tracks are routing
simultaneously. If traces do not appear, press the 3 key to cycle the trace width until it
changes to 10mil.
d) Left-click to place vertical routes. Then, move the cursor and hover above the destination
pad on the far right (Pin 7 of J4) as shown in Figure 269.  If you’re satisfied with the
routes, left-click to place them.

*Figure 269. Multi-Trace Routing from UC1 to J4*
During the Interactive Multi-Routing process, hit Tab and you can set the gap between
the tracks. Or simply press shortcut B to reduce the gap, or Shift + B to increase the
gap as you route. If there is not enough room, the multi-router will not complete the
route.

<!-- p.214 -->

### 21.4.6 Adjusting Tracks

16. If you need to adjust a route, rather than deleting it, we can route it again. Automatic Loop
Removal will remove the old redundant tracks automatically. A good connection to try this on
is the portion of tracks on the Top Layer between J1 and J4.
a) Start a route on the Top Layer from J1 Pad 1 to  J4 Pad 5.
b) Re-route a more direct trace between the two pads.
c) Once the route is finished, the Loop Removal removes the previously routed trace.
17. To drag a track to adjust it, exit the Interactive Router, and left-click the track to drag it.
18. If you do want to delete an entire track and start again, use the Route » Un-route »
Connection, or just press U - U - C and select the track to remove. You can also left-click to
select a segment of the trace and then press the TAB key to select all segments of that track
on that layer
When moving or dragging tracks, we can change its behavior in the Preferences,
under the PCB Editor branch and under the Interactive Routing Page.

### 21.4.7 Contour Follow Mode

This routing method allows you to quickly follow a shape already generated by the board edge, a
cutout or even a through-hole pad or via.
19. In order to connect the 5V net from the J4 connector to the REG3 regulator, we are going to
connect the net using C5.
a) Locate Pad 2 on C5. Begin a route by using the shortcut U »T.
b) Begin routing around the large via located nearest to C5, and as you approach the via,
press SHIFT + F to enter Contour Follow Mode. This should cause the trace to follow the
rounded edge of the via.
c) Route around the edge of the via until you reach the top and click the Left Mouse Button
to set an anchor point.
d) Finish routing to Reg3 Pin 1 (5V) using all methods you have learned so far.

### 21.4.8 Track Glossing

Using some of the interactive and dynamic routing features may leave some undesired track
segments or less effective route paths. We can use Track Glossing to clean up route paths after
placement. Find a route on the PCB that you feel can use some cleanup.
20. To gloss a trace:
a) Left-click to select a segment of the trace and then press the TAB key to select all
segments of that track on that layer. (or Edit » Select » Physical Connection or E » S »
C)
b) Run Track Glossing by going to Route » Gloss Selected. See Figure 270 as an
example.

<!-- p.215 -->

*Figure 270. Gloss Tracks, Before (left) and After (right)*

### 21.4.9 Active Route

21. Select the connection lines between UI1(Pad 1 to 8) and IOS2(Pad 1 to 8) by
holding the Alt key followed by dragging your mouse from right to left around the connection
lines to select them. This will create a selection rectangle and will highlight the connection
lines as shown in Figure 271.

*Figure 271. Select the Connection Lines to route the selected traces*
22. Open the PCB ActiveRoute panel by going to Panels button in the lower right corner and
select PCB ActiveRoute or View » Panels » PCB ActiveRoute.
23. Enable both checkboxes in the PCB ActiveRoute panel Layers section to allow ActiveRoute
to utilize both the Top and the Bottom layer when the command is activated, as shown in
Figure 272 below. However, in our case since we only have SMD Top-Layer pads on UI1
and ActiveRoute does not drop vias, routes will only be placed on the Top Layer.

<!-- p.216 -->

*Figure 272. PCB ActiveRoute routing layer setup*
24. Click the ActiveRoute button in at the top of the panel as shown in Figure 273,
or select Route » ActiveRoute. The routes will be completed as shown in Figure 274.

*Figure 273. Click the ActiveRoute button to start the routing*

*Figure 274. ActiveRoute completed*

<!-- p.217 -->
25. Please continue routing the PCB using the various routing techniques discussed in this
exercise. Use Figure 275 below as a guide. Please bear in mind that the PCB does not have
to be completely routed.

*Figure 275. Routed PCB example*
Routing Tips:
- Use Ctrl + Click on a net object to mask everything but the selected net for better
visibility of target locations.
- Use HugNPush routing mode for routing close to the bus routes or other traces.
- Press Shift + C to clear applied mask after a route.
- Use the bracket keys to increase [ and decrease ] the applied mask and can be used
during routing.
- Holding Shift + Alt while selecting connection lines will accumulate the selection.
