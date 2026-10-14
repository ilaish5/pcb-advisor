# Altium Education (Altium Academy PCB design course) - Unit 4 - Routing and Basic Signal Integrity

> Source: Altium Education course text, English. Curated 2026-10-11: lesson delimiters turned into `## [NN] Title` headings; removed 'Complete and Continue', 'Further Reading' lists (article titles only, no links) and the Quiz lesson (only question 1 was captured). Images are missing, so phrases like 'in the image below' have no picture.

Lessons: [01] Introduction to Routing in a PCB; [02] Routing with Traces; [03] Routing with Polygons; [04] Summary; [05] Designing and Routing With Vias; [06] Via Sizes and Styles; [07] Types of Vias; [08] Annular Ring Diameter; [09] Placing Vias While Routing; [10] Other Via Types; [11] Summary; [12] Routing Different Types of Signals; [13] Choosing Microstrips vs. Striplines; [14] Routing Differential Pairs; [15] Summary; [16] Routing Rules for Impedance Control; [17] Calculating Characteristic Impedance and Trace Width; [18] Using the Layer Stackup Tool; [19] Which Layers Define Ground for Impedance Control?; [20] Design Rules for Routing; [21] Getting to Routing; [22] Summary: Strategies for Routing; [23] How to Use Routing Tools; [24] Interactive Routing; [25] An Example With Vias; [26] Routing Practices to Watch Out For; [27] Simple Differential Pair Routing Example; [28] Routing Three Common Digital Buses; [29] I2C Routing; [30] SPI Routing; [31] UART Routing; [32] Possibility of High Speed Behavior in These Buses; [33] What Makes a Design "High Speed"?; [34] Clock Rate vs. Signal Rise and Fall Times; [35] Impedance Matching; [36] Rise Time and Crosstalk; [37] Summary; [38] Electromagnetic Interference (EMI); [39] Radiated EMI; [40] Conducted EMI; [41] Devices Shouldn’t Interfere; [42] Suppressing EMI; [43] Summary

## [01] Introduction to Routing in a PCB

After placing components, it’s time to start thinking about routing the design. In the previous section, we introduced just a few of the design rules that are needed to ensure your design is manufacturable. Before you start routing the board, it’s a good idea to quickly review a few of the important design rules so that you can route things efficiently. Once the design rules are created, you can get started with routing, and you won’t have to worry about manually checking everything in your layout as you route your traces.

Routing Rules and Strategy in a PCB

In the last section, we looked at the initial placement of components in a demonstration project. Before you start routing, it will be important to decide which components absolutely cannot move in the PCB layout. Some components, like connectors or large ICs that have a heat sink, will need to have a fixed location and should not be moved in the design. Other components can often be shifted as you figure out routing throughout the PCB layout.

Sometimes, you do not know which components will need to move and which components you can leave fixed in your initial placement. Therefore, to prevent the need for a lot of re-routing, it’s important to come up with a strategy for how to approach the board. There is no best strategy for every PCB, but there are some important points to think about:

Using polygons vs. traces: Some nets are best routed with polygons, while others must be routed as traces.
Layer transitions: Which layers will you be routing on, and how many layer transitions through vias will you need to make? Ideally, you should try to minimize the number of layer transitions.
Routing topology: Some signals can be routed as buses, while others must be routed point-to-point. Sometimes, groups of signals need to be routed in parallel (side by side) because data is being carried on multiple traces at once. This is a more advanced rule that we’ll examine in a later lesson.

The most important routing rules to consider in a new design center around three areas: clearances, trace geometry, via size, and impedance. Some of these points are handled inside Altium Designer and other ECAD applications automatically, either through design rules or a setting in your program. The video below will show you how to quickly access and start using the routing features in Altium Designer.

## [02] Routing with Traces

When routing with traces, there are a few points to think about when beginning the process of routing. This first point is to determine the trace width you need, but the trace width you need will depend on whether impedance control is needed:

If the impedance is required to be a specific value, then the width you need will be calculated using the thickness of the dielectric and its dielectric constant.
If the impedance does not need to be controlled, then the trace width should be chosen to ensure easy routing and to prevent design rule errors.

Finally, traces should be spaced apart from each other to help prevent crosstalk. A conservative rule is called the “3W rule”, which states that the spacing between two traces should be 3x their width. This is intended to help prevent crosstalk between the traces, and it works well for many designs. However, when the dielectric between a trace and its ground plane is thinner, you may be able to violate the 3W rule, particularly when you are not working with high speed signals.

Two Common Types of Traces

Some traces that carry signals might require very specific impedance. This is the case for high-speed signals, a certain type of signal that we’ll look at later in this unit. The impedance of a trace is set by calculating the required trace width, but only after you have decided on a stackup for the design. The most common impedance value that is used in electronics, and particularly in PCB design, is 50 Ohms.

The image below shows the most common trace designs: microstrips and striplines. Microstrips are routed on the surface layers, while striplines are routed on internal layers. The solid copper areas are plane layers or large polygons. Your goal as a designer is to figure out what the width should be, either using some formulas or using the impedance solver in your PCB design application.

These are the most common trace styles used in PCBs. There are a few other types of traces, but the majority of your interconnects will be routed as microstrips or striplines. Note that, for striplines, the H values could be different above or below the trace.

It is important to note: not all traces will need to be set to a specific impedance value. These other traces will still be routed in the configurations shown above, but their width may not be chosen to give them a specific impedance. In this case, there are other factors that will determine the best trace width to use for a particular component. The video below provides more information on selecting a width for traces that do not require impedance control.

What Trace Width Should You Use?

The trace width you use in your PCB layout should be chosen based on one of the following three goals:

Hitting an impedance target; we’ll look at this in Lesson 4 in this unit.
Ensuring you can carry enough current; polygons are preferable at high current (more than about 1 A).
Trace density; sometimes, your traces will be densely packed, so you might want to use a thinner trace to make room for all connections.

In general, you can route with any trace width you like as long as it’s within your manufacturer’s trace width and clearance limits. Typical trace widths are 7-12 mils as long as impedance control isn’t required, or as long as you don’t need a wider trace for high current. If you need to set a width to define a specific impedance, Altium Designer has a tool that will set the required impedance for you, so you won’t have to manually calculate and set up a width rule for routing. We’ll look at this aspect of setting up routing rules in Lesson 4 in this unit.

Before continuing in this section, watch the video below. This video will explain some strategies for determining trace width, as well as how to access the trace width settings while routing.

Routing Angles

In general, you can route with any trace angle you like. If you start playing with the routing tools in your PCB design software, you’ll see that it likes to place 45° angles by default. As you start to make a turn while routing, you’ll see how the software places this angle automatically. You can make a full 90° turn using two 45° turns in succession, as shown below.

This arrangement of two 45° angles is the standard way to route a right-angle turn in a trace.

The main reason to stick with 45° routing is that you can generally get the shortest total trace length in the design with these angles. However, there are certainly times where a 90° angle is preferable. There is a longstanding signal integrity myth that 90° angles create a lot of noise in a PCB layout once the device is in operation. This is just a myth that should be ignored in almost all designs. The exception where you will experience problems is in very high frequency designs, such as when the signal frequency reaches 10’s of GHz or higher.

Pad Size vs. Trace Width and SMT Entry

Some components in a design simply have very closely spaced pads, and this will limit the size of the trace that can be used during routing. In this case, you would want to set a minimum width that is small enough so that you can route into the pad, but without getting too close to other pads on the component.

Take a look at an example from the DemoProject we’ve worked on in this course. If you look at the pad width on component U2 in the initial PCB layout, you’ll see the width is 9.843 mils. Also, the spacing between pads is 9.842 mils. Realistically, you could route a 10 mil wide trace into the pads on component U2. However, you could route a larger trace width, but if the trace width is too large, you might violate a pad-to-trace clearance rule.

When the incoming trace is as wide, the SMT entry on this particular component should be straight into the pad, rather than being at an angle. The reason for this is that you might violate clearances unless you are only using a pad in the top corner of the component. This is shown in the above image by the trace being routed directly into the pad.

The other standard way to route into a pad is to use a corner SMT entry. The image below compares corner SMT entry and straight-in SMT entry; both of these cases are appropriate as long as clearances between the trace and the pads are maintained.

With through-hole components, we need to look at some of the same rules we use with vias; we’ll discuss this a bit more below. Through-hole components do not have SMT entry requirements; you can route in at any angle as long as some specific via rules are obeyed.

If another design requirement (current capacity or impedance) requires the trace to have a larger width, you could route a very short section into the pad that is thinner, while leaving the rest of the trace thick. This is a decent compromise between both design requirements. If traces need to be very thick in a design, such as with power rails, it’s better to route with polygons rather than traces.

## [03] Routing with Polygons

Some traces, such as power rails, might carry high current. Copper connections that carry high current are not normally routed as traces. Instead, it might be preferable to route these as polygons. Using a large copper polygon gives you a lot of freedom to choose the shape and size of the connection. PCB design software constrains how traces are defined such that they have very specific width, and this might mean you have less flexibility to route traces in the way that works best for your design.

Take a look at the example from Layer 14 in the MiniPC project below. The pink, purple, and dark green regions are power nets, each at a different voltage or making a specific set of connections in the design. The remaining light green area is ground (GND). These regions are not defined using the trace routing tools in Altium Designer, they are drawn out as polygons.

The polygon tool in your design software is preferable here as you would never be able to route the above example as a trace. PCB design tools will define traces with curved ends, and they will often place 45° angles as you try to route the connection. Using a polygon for routing is preferable as you can create a totally custom region of copper as you create your connection.

Watch the video below for an example of using the polygon tool in Altium Designer.

Although polygons are often used for power connections, they can also be used for ground connections. There are also times where they can be used for generic DC connections that are not necessarily for power. If you need to design a very specific copper structure for an RF circuit (such as an antenna or filter), you would want to do so using a polygon.

In general, you can assign a polygon to any net. In Altium Designer, you’ll do this in the Properties panel. The advantage of using a polygon is that they can easily make connections between a large number of components with a single piece of copper. An example for one of the power nets shown in Layer 14 of the MiniPC PCB layout is shown below.

The purple polygon in this image is assigned to a 12 V power net. Using a polygon for routing here is preferable to placing traces because the polygon can connect to all of these vias very easily.

Another example that shows the advantages of using a polygon over traces is shown below. In this example, the 3V3 net is routed with traces and has been split in the center of the screen so that power can be routed to different traces. A polygon could be drawn across all the pads to route power instead of using traces. Since this is a power net, a polygon would be preferable as it can provide more current than a trace.

In the above image, you’ll notice the via at the top of the image are much larger than the size of the nearby traces. Is this normal, or are these vias too large? This is an important aspect of routing that we will look at in the next lesson.

## [04] Summary

Summary

In this lesson, we’ve looked a lot at trace width and whether to use traces vs. polygons for routing. However, there are other routing rules to consider in your design, and these typically apply in very high speed designs. These include leftover stubs on vias, via styles, and some others. We’ll look at some of these in more detail later in this unit, particularly when we look at high speed designs. In addition, we will look at how to access and use the routing features in Altium Designer.

## [05] Designing and Routing With Vias

Without vias, we would not be able to route multilayer PCBs. Vias are used to make transitions between layers in a design, so you will need to use them during layout and routing in a double-sided multilayer board. The challenge with vias, particularly among new designers, is they are often sized incorrectly such that they are un-manufacturable as designed. In addition, you might be too conservative and use vias that are simply too large, which can make routing more difficult than it needs to be.

If you look back at the example layouts in the previous lesson, you’ll notice that every example has some vias. Just like traces need to have the right width, vias need to have a diameter that conforms with the trace width, and to the pad size they are connected to. When vias are used to make connections back to components, the vias need to be properly located so they do not interfere with assembly. We’ll look at all these aspects of vias in this section, as well as how you can and access them during routing.

## [06] Via Sizes and Styles

If you just look at a via in a PCB layout, it is not always obvious that you are actually looking at a via. Take a look at the layout image below. All vias have two elements that must be defined correctly in the design: the drilled hole diameter, and the pad or annular ring. The terms “pad” and “annular ring” are sometimes used interchangeably. When you look at a via in your PCB design software, you’ll be able to clearly see the pad and hole as different colored areas. The net name should also be visible. If the via is part of a component footprint (e.g., a through-hole component), then the pin or pad number should also be visible.

Your job as a designer is to balance the trace width you’re using with the appropriate via size. If you want to ensure your board can be fabricated by any manufacturer, you should use no smaller than 8 mil drilled holes in your vias. This is about the smallest hole that can be mechanically drilled in a PCB during fabrication; smaller holes are more specialized and may require laser drilling. Once the via is plated, the plated hole diameter will be slightly smaller than the drilled hole (about 1-2 mils less).

An example of a situation with a large trace connecting to a via is shown below. Here, we have two traces coming off of an SMD pad and being routed into a ground plane through vias.

In this example, the connecting traces are only 15 mils wide, but we could have made them as large as 20 mils. This would match the size of the 20 mil pad.

Just like SMD pads have an entry point and angle to consider, so do vias in a PCB layout. The trace that is connected to the via should ideally route straight into the annular ring to make a solid connection, as shown above.

Your traces might be somewhat smaller than the drilled hole diameter, either due to an impedance requirement or because you’re routing into a very dense component (see the FPGA example in the previous lesson). This is okay; you can use traces that are smaller than the via hole because the traces are making a connection to the annular ring/pad. As long as the pad is large enough, you won’t have a problem with reliability.

An example is shown below, where the drilled hole for the via is much larger than the trace width: this is appropriate too, but much more care should be taken to ensure the via entry is straight in and not at an angle. This situation is typical in a controlled impedance design that requires thin traces; you don’t have the freedom to use a thicker trace, but you need to use at least an 8 mil via hole, so you’re forced to use the routing style shown in the image.

The routing tools in Altium Designer will help prevent the type of routing on the right in the above image. However, if you have an existing trace, and you place a via on that trace, it’s possible to put the via hole offset from the trace, giving the un-preferred routing shown above. Watch out for this when placing vias as the un-preferred routing shown could create a reliability problem during manufacturing cue due to drill wander, and your fabricator may send the design back for corrections.﻿

## [07] Types of Vias

Types of Vias

All vias in a PCB come in three possible styles:

Through-hole via: These vias span through the entire thickness of the board. They can be plated, meaning they will allow signals to conduct between the board, or they can be non-plated, which will not conduct any signal.
Blind-via: A blind connects a surface layer to an internal layer, but the via does not pass all the way through the PCB to the other surface layer.
Buried-via: A buried via only passes between internal layers, but it does not make any connection to the surface layer. Thus we like to say the via is “buried” inside the PCB stackup.

There is a fourth type of via, called microvias, which are very small compared to the other types of vias placed in a PCB. In general, microvias are blind, buried, or stacked arrangements of blind/buried vias. These vias are drilled with a laser and can be as small as 3 mils. Because they are so small, and the wall plating is so thin, they cannot span more than 1 layer, and they are only used in very high layer count PCBs.

## [08] Annular Ring Diameter

As we mentioned earlier in the course, via holes are drilled into the PCB during fabrication, so the vias need to be sized to match standard drill sizes. This is where it’s best to work in units of mils: standard drill sizes are set in whole numbers of mils (10, 11, etc.). Mechanical drilling can be used to place vias down to approximately 8 mils diameter, while 10-12 mils is most common. Smaller via sizes require a specialized laser drilling process. In general, smaller drill sizes will be more expensive to fabricate.

When selecting which via sizes to use, you should compare the trace width you’ll use to the via width and the annular ring that will surround the via. Once the via diameter is determined, the via’s annular ring should be sized so that the via connection will be reliable. The IPC-6012 standards define three performance classes that are implemented in rigid PCBs. The vias in these PCBs must be sized so that they can always be fabricated despite any variations in drill location that might occur during fabrication. These are outlined as follows:

Class 1: Throwaway products that are not intended for long-term usage. These products do not have annular ring requirements for vias.
Class 2: These electronic products are intended for long-term use and must be reliable. IPC Class 2 requires an annular ring be at least 4 mils thick. In other words, via’s pad diameter must be at least the drill diameter + 8 mils.
Class 3: These products are deployed anywhere human lives would be put in danger should the product fail. IPC Class 3 requires an annular ring be at least 5 mils thick. In other words, via’s pad diameter must be at least the drill diameter + 10 mils.

These three IPC performance classes have many more requirements than just annular ring sizes, but violating Class 2 or Class 3 annular ring specifications is a common reason a design may not pass a manufacturer’s DFM review before fabrication.

## [09] Placing Vias While Routing

Once you’ve determined your IPC-A-610 class level and the trace widths you’ll use, you can start to route your board and place vias as you run traces between components. The video below shows some ways you can access and place vias while routing your traces.

The question you need to think about is how to use vias in the routing process. Vias are useful for getting around obstacles as you route your board, so it’s important to include them in your strategy for building connections. Vias are also needed on power and ground nets in order to reach plane layers.

Teardrops on Vias

Some fabricators will recommend you place an object called a teardrop on a via pad. The idea here is to increase the reliability of the via by adding some extra copper that smoothly transitions the trace into the pad. An example is shown below.

The curved portion of these traces (selected and shown in purple) are teardrops.

During fabrication, a CNC drill can have some drift and hysteresis, and it is possible the drill does not hit exactly at the center of the pad as defined in your PCB layout. Having teardrops on vias ensures the connection between the trace and the pad is not destroyed in the event the drill does not hit at exactly the right place. If you designed the trace and annular ring to the same size, then you won’t need teardrops.

To add teardrops to a trace and pad, follow the instructions in the video below.

Does Via Impedance Matter?

Unlike traces, most designs won’t require you to calculate the impedance of a via. An example where via impedance is important is in very high frequency PCBs or a very high speed design, which might require that all vias have specific impedance. In most designs, the most important consideration is making the diameter small enough that you can conveniently place vias between traces and components. If a via is too large, it might violate clearances, or it can make routing on other portions of the design more difficult.

We’ll talk more about the potential problems with vias and their impedance when we look more at high speed design later in this unit.

## [10] Other Via Types

Other Via Types

The types of vias mentioned above are the basic types of vias placed in PCBs. There are other variations on these standard via structures:

Tented vias (covered): These vias are covered with solder mask; tenting might be used if a via is placed very close to a large pad and there is the potential for molten solder to wick onto the back side of the board during assembly.
Via in pad: These vias are placed directly in the pad of a component; this is common in high density designs, particularly designs that use very dense BGA components.
Via in pad plated over (VIPPO): These vias are filled and plated over with copper; doing this prevents any wicking of solder or passage of flux residue contaminants through an open via hole.
Plugged vias: These vias are filled with a non-conductive epoxy; doing this eliminates the need for a surface finish in the via barrel.
Filled vias: These vias are filled with a conductive paste material, which is then hardened; this gives a via structure with higher current capacity.

## [11] Summary

With traces and vias, you now have the two essential tools you need to route traces throughout a PCB layout. We’ve mentioned impedance multiple times in this unit, and the next unit will give a greater explanation on impedance of different trace designs that can be used in a PCB layout.

## [12] Routing Different Types of Signals

So far, what we’ve presented about electrical signals and routing between components focuses on a specific type of signal and trace arrangement. In particular, we only looked at an individual trace that gets routed on its own; the only other important element needed to define the voltage carried by a signal is the ground plane.

In this lesson, we’ll explore these different trace routing styles (single-ended vs. differential), as well as the signals that they carry. We’ll also look at some of the important points to watch in your board to ensure signal integrity.

Single-ended Traces vs. Differential Pairs

Before discussing anything with impedance, we need to look at the two main types of signaling in PCB design: single-ended signals and differential signals. These are routed on single-ended traces and differential pairs, respectively.

Differential pairs are often discussed in terms of high-speed design, something which we will look at later in this lesson. Most of the standard computer interfaces (like USB, Ethernet, HDMI, and many others) are routed on a PCB using differential pairs. However, there are other digital signal protocols that are low speed but are still routed as differential pairs. Meanwhile, some buses that are at the very edge of being considered high speed are still routed as single-ended signals.

Single-ended traces are simple: this just refers to a trace routed along a specific layer, ideally above a ground plane. The voltage carried by the signal in this case is measured between the trace and a ground plane. A differential pair uses two traces routed side-by-side to carry a digital or analog signal between two components. The signal is carried as two equal and opposite signals routed on the traces (V+ and V- in the above image), and the voltage carried by the signal is measured between the two traces.

The image below shows an example to illustrate how differential pairs and differential signaling works. Suppose our digital signal carries V1 = 350 mV. In a differential pair, there is an equal and opposite copy of the signal on the 2nd trace, which has voltage V2 = -350 mV. When the differential signal is collected by the receiving component, it is measured as 350 mV - (-350 mV) = 700 mV.

Differential pairs can be microstrips, as shown above, or they can be routed on an internal layer as striplines. When planning out routing for either type of signal, you’ll need to decide whether you’ll route on the surface as microstrips, or an internal signal layer as striplines, for both types of signals. We’ll look more at some design rules for differential pairs later; for now we want to look more about incorporating these into our routing strategy.﻿

## [13] Choosing Microstrips vs. Striplines

The previous image shows traces on the surface layer (microstrips), but you could also elect to route in an internal layer (striplines). The question now becomes: which routing style should you use? In general, you can use either type of trace routing to make connections between components.

One important piece of information that is sometimes overlooked is:

Components and interfaces determine whether you have to use differential pairs. As the designer, you get to choose where you route them (internal vs. surface layer).

Some of the advantages and disadvantages for each type of trace routing configuration are shown in the following table.

	Microstrip	Stripline
Losses	Lower losses than stripline	Higher losses than microstrip
Shielding against electromagnetic interference (EMI)	EMI shielding can be low, but it can be increased by using ground pour	Striplines have EMI protection due to the nearby ground planes
Trace width	Wider than stripline for specific substrate thickness	Thinner than a microstrip with same plane-to-plane substrate thickness
Signal speed	Signals travel faster	Signals travel slower
Radiation and crosstalk	Stronger radiation measured away from the board	Lower radiation, although high frequencies can emit strongly

In many cases, you will have the freedom to choose to use stripline or microstrip routing as long as you will dedicate the appropriate layer to routing these signals. Take a look at the example stackup below. This stackup includes 6 layers; microstrips can be routed on the top and bottom layers, but there is also one available layer for stripline routing (SIG/PWR, or Layer 4).

Some components, like a large processor, will require some stripline routing and microstrip routing simply because there are so many pins on the component. Take a look at the below example: this image shows a portion of a PCB layout with a large FPGA component. This FPGA is a 676 pin processor with a ball grid array (BGA) footprint.

The component requires multiple power and ground connections, and these connections are interleaved with the various signal connections on the top and bottom layers. While it may not be obvious from this view, this FPGA is placed on the stackup shown in the previous image, and it requires signals be routed on L1, L4, and L6.

This large FPGA requires routing on multiple layers in order to route all the required signals. The various signals and the layers where they are routed are highlighted in different colored boxes around the edge of the component. The remaining vias in the central region of the component are routed to power and ground on L2, L3, and L5.

In the above image, you should be able to see how traces come off in pairs; these pairs of traces are differential pairs. This component includes interfaces that require differential pair routing, and this is why differential pairs appear in the layout. We’ll look at more examples with this layout in this lesson.

If you’re ever unsure of which traces are differential pairs, you can always zoom in until you see the net names; both traces in a differential pair will always have the naming format “NetName_P” and “NetName_N”. The “_P” suffix tells you the trace is the positive side of the pair, and the “_N” end tells you the trace is the negative side. The following image shows two of the pins on the FPGA, but with the view zoomed in until the net names can clearly be seen.

The above images with the FPGA show just one of many examples where routing on multiple layers is needed in order for all signals to be accessed and connected to various components. Large processors like FPGAs, MCUs, and CPUs will all make use of this type of footprint and routing because it is the only way to keep the component size small while also allowing multiple connections to be made in the layout.

## [14] Routing Differential Pairs

Here are some general rules for routing differential pairs:

The pairs should have as close to the same length as possible within some tolerance. This helps ensure you get maximum common mode noise reduction at the receiver and that signals will be read out properly.
The traces in a differential pair need to be kept a specific distance apart from each other, and that distance should be maintained throughout the routing path if you’re following the differential impedance specification. This distance will determine the impedance of the differential pair and the impedance of each single-ended trace.
Just like with single-ended traces, it’s preferable to route short, direct routes between components when possible.

PCB design tools will route the differential pairs together in order to keep the required width and spacing. The routing tools in Altium Designer will enforce these limits based on your design rules. As you route, remember that you can display the clearance boundaries around nearby traces with the Ctrl + W shortcut. Clearance boundaries are shown using a white outline around nearby traces and other objects while you route (see below).

When you create an impedance design rule for your differential pairs, you’ll be able to enforce the first two rules above automatically; we’ll look at this in the next lesson. Now we need to look at length matching structures, which you can see in the above image with the large FPGA.

Length Matching Structures

Sometimes, you can’t make the lengths of your differential pairs match perfectly during routing. When this is the case, you will need to apply length matching structures in the design. These appear as meandering curves during routing. An example for a differential pair used for Ethernet routing is shown below.

Ethernet routing with length matching using differential pairs.

Why do we need to apply length matching structures? The reason has to do with how signals on differential pairs travel on the line. The two signals need to be changing between OFF and ON states at the same instant. This way, the two sides of the pairs will have signals arriving at the same time, and the voltage between the two traces will be measured to have the correct value. This also ensures that any noise being carried along the traces can be canceled out at the receiver:

By adding a length matching structure to the shorter trace, you delay the arrival time of one signal so that it arrives at the receiver at the same time as the other signal.

The above example with Ethernet routing uses differential pairs, but there are also times where you need to apply length matching to groups of single-ended traces! This occurs when you have a group of traces that carry signals in parallel. The most common instance where this occurs is with DDR routing, as shown below.

These length matching structures between the FPGA and a DDR RAM module ensure all signals needed to access data will arrive at the RAM chip at the same instant.

One point to note is that you don’t need perfect length matching in differential pairs (or parallel buses of single-ended traces). Realistically, you just need to get within some tolerance. This is one aspect of differential pair design that is more advanced. If you are using FR4 laminates, you can usually check your component datasheet and calculate the allowed length mismatch for these designs.

## [15] Summary

In this section, we’ve looked at the two primary types of routing styles used in PCBs: single-ended signals and differential signals. Both types of routing might require an impedance rule be set for the traces, which will always restrict the width of the traces to a certain value. Before you start any routing, you need to note which traces will need specific impedance values. We’ll look more at this specific aspect of routing in the next lesson.

## [16] Routing Rules for Impedance Control

So far, what we’ve presented about electrical signals and routing between components focuses on a specific type of signal and trace arrangement. In particular, we only looked at an individual trace that gets routed on its own; the only other important element needed to define the voltage carried by a signal is the ground plane. Together the trace geometry and the ground plane define a very important electrical quantity of PCB traces: the impedance seen by a traveling signal.

In this lesson, we’ll explore the various factors that affect the impedance of a PCB trace. Once you’ve determined the impedance you need for your traces, we can apply the impedance you’ve determined as a design rule. Once you’ve set up these design rules, you can start routing some of the more complicated computing interfaces on a PCB, such as USB or HDMI. We’ll also look at setting up design rules for length matching in differential pairs, and how to apply length matching in a PCB layout.

Trace Geometry and Impedance

In Lesson 1 of this unit, we briefly looked at the concept of impedance in PCB traces. Single-ended traces have a characteristic impedance that is used in signaling standards, and it needs to be calculated to ensure signal integrity at the receiving end of the trace. When designing a PCB that requires specific impedance on some traces, there are some important factors that determine characteristic impedance for traces in your PCB. 

A specific distance from a trace to a ground plane will require a specific trace width in order for the trace to have a target impedance. This is why you want to set a trace width only after you decide on a stackup. If you go back and change the layer thickness in the PCB stackup, you may need to change some trace widths in order to make sure you hit your impedance targets on certain nets.

The geometric variables needed to hit a specific characteristic impedance or differential impedance depend on the stackup. The main parameter is the thickness of the dielectric.

Microstrips are shown above, but the same idea applies to striplines. Now, we want to look at how you can actually calculate the trace width you need to hit a specific characteristic impedance value (for single-ended traces), or the width and spacing you need to hit a specific differential impedance (for differential pairs).﻿

## [17] Calculating Characteristic Impedance and Trace Width

First we should note, there are online calculators you can use to calculate the trace width needed for a PCB. These trace width calculators or impedance calculators are based on two possible sets of formulas. The most common formula that relates impedance to trace dimension is from the IPC-2141 standards:

These formulas only apply to two trace arrangements: microstrips (top) and striplines (bottom). Here, h and B are layer thicknesses, and t is the thickness of the copper trace, which can be calculated from the weight. The units used in these equations are not important, although mm or mils are generally used. A convenient table you can use to convert copper weight to copper thickness is shown below:﻿

Copper weight	Thickness (mil)	Thickness (microns)
0.5 oz/sq ft	0.671	17.05
1.0 oz/sq ft	1.34	34.1
2.0 oz/sq ft	2.68	68.1
3.0 oz/sq ft	4.02	102.2

The microstrip equation is simple enough that it can be solved for the trace width w; if you solve for w, and you plug in the values of h, t, and Z0, you can calculate the required value of w. The other equation is much more complicated and cannot be readily solved. The above equations are for single-ended traces, but there are no good formulas for differential pairs. Once you look at a coplanar microstrip or a coplanar stripline, where copper pour runs next to the trace, the impedance equations are even more complicated.

There is an alternative set of equations that can be used to relate impedance and trace dimensions. These equations are published in Brian C. Waddel’s textbook Transmission Line Design Handbook. These equations are more accurate than the IPC-2141 equations shown above, but they also require a numerical solution method to determine the required trace width needed to hit a specific impedance.

Differential Impedance

With differential pairs, we have another parameter to consider: the spacing between the two pairs. Differential pairs will have an additional impedance value: the impedance of the pair when measured together, or the differential impedance.

This graphic shows how the characteristic impedance is defined and measured. Single-ended traces have characteristic impedance that is defined between the trace and its ground plane. Differential impedance is defined between the two traces in the differential pairs.

Because there are no widely accepted closed-form equations that can be used with differential pairs, calculator applications are normally used to determine the differential impedance.

## [18] Using the Layer Stackup Tool

Today’s PCB design tools will include some kind of calculator that can be used to calculate impedance. You will normally use this tool when you design and finalize your PCB stackup. This is because, as we briefly mentioned in the previous lesson, the thickness of the layers and the copper weight in a layer will determine the trace width needed to hit a target impedance.

Instead of doing all these calculations by hand, modern PCB design tools can calculate the required trace width for you automatically based on your chosen stackup. These tools are more accurate than the IPC-2141 equations and Waddel’s equations, and they can account for some process-specific factors in a PCB stackup.

In Altium Designer, the Layer Stack Manager includes an impedance solver that can be used to calculate the width needed for a specific impedance. If you look along the bottom of the Layer Stack Manager window, you’ll see an “Impedance” tab.

From here, you can access a utility that allows you to calculate the trace width needed for single-ended traces, or the width and spacing needed for differential pairs, on any layer of the PCB. The video below shows how to use this tool and gives a brief overview of how it applies to different types of trace geometries.

## [19] Which Layers Define Ground for Impedance Control?

When we use the term “impedance control” or “impedance controlled routing,” we’re referring to a design where traces that have specific impedance

If you look in the above video and stackup, you’ll notice that there is an important piece of information that needs to be tracked when calculating impedance: the location of the reference plane in the PCB stackup. This is important as it relates to the value of H in the IPC-2141 formulas: it tells you the distance between the trace layer and the ground layer.

Why is the reference plane important? When we say reference, we are technically referring to a ground plane, or a layer in the PCB with some grounded copper pour. If you remember your introductory electronics classes, you’ll remember we need two points to define a signal measurement, and one of these is a reference or ground connection. When a signal reaches a component, the voltage/current that is carried by the signal is measured with respect to the ground net in your PCB, as illustrated below.

This image shows a signal traveling between two components, starting from the source end and traveling to the load end. By routing over a single ground region in the PCB, the signal level at the source (VS) will have the same value as measured at the load (VL).

If the trace needs to have a specific impedance value, then that value should be calculated using the ground net for the source and load components in the interconnect. What you should not do, is have the signal begin from a source over one ground region, but then have it collected and measured by a load over a different ground region.

When the traveling signal crosses a gap between two different ground regions, there is an impedance discontinuity between the two components. It’s also possible that the signal voltage as measured at the source and load are not the same because the ground potentials in each region are different.

The problem is that, in the transition between the two regions, we will have an impedance discontinuity, where the impedance is not maintained at the same value between the two ground regions. In addition, because ground regions are not always as the same reference potential values, the signal level may be measured to have a different value at the load than at the source.

For this reason, we have one important rule to highlight when routing with time-varying signals:

Always route traces with digital or analog signals over a ground plane or large grounded polygon.

With DC traces, this requirement is less strict unless your board is deployed in an environment with excessive noise.

Because of the problem with signal level measurements in different ground planes or grounded polygons, we have another important design rule:

Connect all ground regions used to support routing together with vias or direct connections with copper.

There are a few other reasons to obey these routing rules; we’ll discuss these in a later lesson on signal integrity in this unit.

## [20] Design Rules for Routing

We should already be able see a few possible important design rules that will need to be defined for single-ended traces and differential pairs:

The required width of each trace
The spacing between traces (important for differential pairs)
The maximum allowed difference in the length of each trace
Maximum deviation from the ground plane

The impedance profiles we created in the above tutorial apply to the first two points. These values for trace width and spacing in differential pairs are enforced by creating a design rule.

Setting Up Net Classes and Impedance Rules

A “Net Class” is a grouping that is defined in many ECAD tools. This grouping is something that you, as the user, get to create to help you keep your traces and signals organized. It also lets you apply design rules to an entire group of traces at once. This is really important because, in some cases, you might have a group of dozens of nets, and they might all need to have the same design rules.

Altium Designer uses Impedance Profiles to store the width needed for a target impedance on each layer. The impedance profile is created in the Layer Stack Manager, as shown in the video above. When  you want to assign the impedance profile to specific nets, open up the PCB Rules and Constraints Editor, and navigate to Routing → Width. A similar set of design rules for differential pairs can be accessed from the Routing → Differential Pairs Routing rule.

Impedance Profiles can be assigned to specific nets in this window.

What if you have a large number of nets that all require the same impedance profile? You don’t necessarily need to create a single design rule for each net in your design. Instead, the best way to group nets together into Net Classes is to group them by signal and interface type. For example, we would only want to group nets for USB routing with other USB nets, we would only group Ethernet nets with other Ethernet nets, and so on. Different types of differential pairs may have different impedance values, so they will need different design rules.

If you’re unfamiliar with Net Classes, watch the video below for a tutorial on setting up these design rules before you start routing impedance-controlled nets.

To do enforce the design rules for differential pairs, we need to complete four tasks:

Determine the allowed length mismatch for an interconnect
Set the appropriate differential pair naming scheme in the schematic
Create a Net Class (group of nets) that only includes specific groups of traces or differential pairs
Define the differential pair impedance in the PCB stackup
Assign the differential pair impedance value to a net class in the design rules

﻿The video below shows the process for setting up impedance controlled differential pairs. This follows a slightly different process and design rules based specifically on defining differential pairs in the schematic and the PCB layout. As long as the differential pairs are properly defined in the schematics, named correctly, and assigned to a Differential Net Class, the standard differential pair routing rules can be used successfully and the differential impedance profile can be applied to these nets.

Finally, we need to create a differential pair length mismatch design rule. This will define the allowed mismatch between the lengths of the two traces in the differential pair. The process for doing this is shown in the next video.

## [21] Getting to Routing

Once all your design rules are set up for impedance controlled traces, you can start routing everything in your PCB. The routing portion of the design process can be the most time consuming, but getting it right helps prevent distortion in your signals so that the design will function properly.

In Altium Designer, there is no separate “microstrip routing” or “stripline” routing command. Everything is done with a single routing command, and the trace will appear in the layout depending on which layer is currently active in the PCB Editor window. The same functions are used in other design applications to help speed up the routing process.

The primary routing features you’ll use are the Interactive Routing and Interactive Differential Pair Routing tools, located along the top bar in the PCB Editor in Altium Designer.

The interactive routing features are the primary features used to route a PCB. Just like these tools don’t differentiate between microstrip and stripline routing, they also don’t differentiate between impedance controlled routing and regular trace routing. If impedance control is needed, the routing tool will automatically apply the required trace width as soon as you start routing an impedance controlled net in the PCB layout.

## [22] Summary: Strategies for Routing

Although there aren’t different microstrip and stripline tools, there are different tools for single-ended and differential pair traces. Before starting routing, there are some strategies you should use to plan out your routing and potentially reduce the total time needed to route your board.

Obviously, we’ve gone over many rules and strategies for routing traces in your PCB layout. To summarize, here are some of the main points to consider and follow when routing:

Ground plane: Modern designs should use a ground plane. This means you don’t need to route ground connections on the surface layer, you can connect directly to the ground plane with vias.
Gaps in planes or polygons: DC traces are fine to route over gaps in ground planes or polygons in some cases, but other digital or analog signals should not be routed over gaps in ground planes.
Plan to route groups of nets on the same layer: Try to pick out groups of components in the design that can have direct connections for routing and solve those first. Routing has a 90-10 rule: the last 10% of routing takes 90% of the time. Solving the easy stuff first will help you get through most of the routing quickly.
Differential traces on the same layer: Because differential pairs require the same trace lengths, it’s best to route them both on the same layer. This ensures you have correct length matching because the signals have the same speeds.
Don’t be afraid to shift components: As you work through routing, it’s always possible that you need to shift the placement of components in the design to ensure all nets can be routed properly. Don’t be afraid to shift or rotate components as needed to make sure you can finish routing the design.

As for other routing rules, the main rules we want to consider for now are trace width. There are a few reasons for this, which are discussed below. You can find all of the routing design rules in the “Routing” section in the PCB Design Rules and Constraints window in Altium Designer. If you have not looked at how to define clearances in a PCB, look again at Unit 3, Lesson 6 and Lesson 5.

## [23] How to Use Routing Tools

After placing components, setting up some impedance rules, and setting some of the basic design rules needed for your project, it’s time to start routing some of your signals. If you’ve taken time to follow the previous sections and layout components appropriately, routing will be much easier. In addition, if you haven’t set up your design rules, it’s important to do so, especially if you need impedance control.

Routing Single-ended Traces

Just as was the case with component placement, there is no single way to route every PCB, whether with single-ended traces or differential pairs. However, we can offer some guidelines to help you get started.

To see some strategies for beginning routing in a PCB, let’s look again at the initial component placement in your DemoProject PCB. If you open up the project from your Altium 365 Workspace, you should see the unrouted component arrangement shown below.

Before you start routing any traces, think about where you’ll place some of the basic connections. Since this device is a power regulator, want to think about:

Where will we be placing input and output power connections?
Which components are close enough to each other that they can be quickly connected?
Do components share nets such that they can be quickly connected with traces or polygons?
Are there any components that can be moved to satisfy the previous three points?

The reality is, very few layouts will ever be routed without the need to move at least some components. Just remember that it’s okay to move some of the components around during routing as long as they are not essential for some reason.

Different ECAD programs have different routing tools, but they are all designed to allow a point-and-click workflow. As we saw briefly in the previous lessons, these tools can automate some of the tasks in routing like placing corners and setting trace widths.

## [24] Interactive Routing

The Interactive Routing tool in Altium Designer is the main tool you’ll use to route single-ended signals. This tool lets you simply point and click your way through routing. As you work, you’ll still be able to access features like zoom in/zoom out, or you can pause during routing to access a via, change trace width, or simply leave an incomplete trace.

As an example of how simple it is to route components, take a look at the animation below. In this example, we can simply select the tool and click between different points in the layout to place the trace around the PCB layout. In the first step, the “Texts” entry on the View Configuration → View Options panel has been disabled so that the component reference designators don’t clutter up the layout.

If you look closely, you’ll see that there are some components that could be moved in the PCB layout to help expedite routing. If you look at R1, R2, C1, and U1, you’ll see that these all connect to net V_IN. This is the input voltage net for this board, so it would make sense to put these nets together in a centralized location near the left side of the board. Instead of immediately routing, it might make sense to move R1 and R2 first as this can help make the layout more compact.

If we rotate R1 and R2 by 180° and move them over to the left area of the board, we can make part of the routing a bit easier, as shown below. We could also rotate R2 and place it near the top of U1 so that the Vmon1 net can be routed between R2 and U1. By making this simple change, we can more easily route the Vmon1 net between R2 and U1 without using a via.

This place-and-route process is common in boards that do not have very strict component placement requirements. Although the connection between R1 and U1 is also routed in the above animation, routes like this are not always preferred. As we’ll see later in this course when we run through a more detailed example, this trace could best be routed using vias.

## [25] An Example With Vias

It’s also advisable to plan out how you will make connections with vias see where vias might fit into these routing strategies, we can move some of these components closer together. You’ll notice that U2 also has a connection to V_IN, so we would want to move it closer to the left side of the board so that it can be easily accessed.

If you follow these steps, you’ll see that +3V3_EN, V_IN, and GND will have to cross over each other in the layout. This is a great example of something we can solve with vias. Since V_IN will need to make a connection with multiple pins on different components, we’re better off using vias to route GND and +3V3_EN through a different layer (in this case, Layer 2).

To do this, you would simply place vias near the pads where you want to make a connection to an internal layer. After assigning each via to the desired net in the Properties panel, you can route directly from the particular pad to the via. This has been done for nets GND and +3V3_EN (shown with white arrows)

The other way to place these vias quickly is to start routing with the Interactive Routing tool, then select a via mid-route, and place this via exactly where you want it in the layout. The idea now is that you can connect the two +3V3_EN connections with a trace in the next layer.

You can then make GND connections with a large polygon. By applying the above trace and via to all pads that are assigned to the GND net, you connect all of these points by placing polygon pour throughout Layer 2.

A Note About Autorouters

One point we should note: many ECAD programs include a tool called an autorouter. These tools are designed to provide automatic routing with the intent of saving you time and effort creating your PCB. However, many professional designers do not use or recommend autorouters for several reasons.

Generally, autorouters can only solve simpler layouts that do not require so much effort for an experienced human designer. In addition, the routing created by these tools can require a lot of cleanup to ensure traces aren’t too long, too dense, or have too many layer transitions. Once you enforce these points as design rules, most autorouters won’t be able to complete complex routing tasks, leaving you to finish routing by hand. For these reasons, we won’t look more at autorouters in this course.

## [26] Routing Practices to Watch Out For

Just as there are some important things you should do when routing, there are other things that are important to not do when routing. Some things you should remember when routing are included in this section. The examples shown below involve single-ended signals, but they also apply to differential pairs.

Don’t Route Back and Forth Around the Board

If you’ve laid out components appropriately, you won’t be in a position to need to route back-and-forth across the board in order to make your required connections. To see what this means, take a look at the example below. This example is an alternative way to layout 3 of the components in the DemoProject PCB we’ve looked at in earlier lessons.

In the above image, we have three of the components laid out in a long line as an example. Two of the problem nets are drawn out in blue. This layout breaks one of our rules in component placement because one of the nets intersects with U2. In this case, we would have to route across the board, then back across/around U2, in order to make the required connections.

Remember, this board was being designed to carry power from the input (left side) over to the output (right side). If you look closely, you’ll see that the right side of R1 and R2 connect to the V_IN net, so it wouldn’t make any sense to orient these to the output side of the board. Even if we did rotate these around 180° so that the V_IN connections face the left side of the board, we would still have to route V_IN all the way to the right side, then back to the left side on the lower blue line to make other required connections.

The moral of the story is: if you find yourself in a position where you need to route back-and-forth across the board, you might want to change component placement. The goal is to ensure traces are short and direct whenever possible. Also remember, you don’t have to route everything on the surface layer. If you place components closer together, and there is still some crossover between nets, you might have to use vias to complete the routing.

Plan to Route Traces in Buses Together

When you’re creating your design, you’ll notice many common acronyms that will be used to denote signaling standards. Two common bus standards for digital designs are SPI and I2C, although there are other standards that are common in digital systems. In high speed PCBs, other interfaces like DDR and PCIe are used.

When we say “route buses together,” we mean that you should leave space on the board for all of the traces that make up the bus to be routed as a group, ideally on the same layer. Component manufacturers have realized the need to do this with their components and will provide some support by placing these pins together on a component. An example with the STM32F429NEH6, a popular microcontroller, is shown below. In this component, the SPI bus pins are placed along the outside of the component for easier access, as shown in the footprint image below.

These traces are best routed together along the same general path, and the same layer if possible. As these particular traces are not generally high-speed signals, they don’t require controlled impedance. Just as an example, the two intervening pins could be routed through vias, while the other pins could be directly connected to traces on the surface layer and routed to the destination component.

In some parallel bus interfaces, especially in a high speed interface like DDR, these groups of traces can take up a significant amount of space due to the large number of traces that make up the bus.

Don’t Route Over Splits in Ground Planes

This is more important in high speed digital signals, although today’s digital components all run near the border of what could be considered “high speed;” this is something we’ll discuss in more detail in a later lesson. Traces that are used to carry a digital data stream, even those that do not run at very high speeds, should be routed over a ground plane, or at least over a large ground polygon, on an adjacent layer.

An example of this type of routing is shown below, where a trace is routed over a split in a polygon. This type of situation is easy to spot if you simply have the routing layer and the neighboring ground layer turned on; you’ll be able to spot when you’ve routed over a split in the neighboring ground layer.

An example from the above STM32 layout is shown below. The traces in the top layer (Layer 1, in red) are carrying a digital bitstream and are being routed over a layer with grounded polygons (Layer 2, in blue). The split in the ground region can be seen clearly when layers 1 and 2 are turned on (set these to Visible in the View Configuration panel in Altium Designer).

Here are some guidelines for determining when this type of routing is appropriate:

If the trace carries a digital bitstream, or it carries a PWM signal that would be used in a switching voltage regulator, it should always be routed adjacent to an unbroken ground plane.
If the trace carries a signal that needs to infrequently change from low voltage to a logic level, like a configuration pin on a microcontroller, you can sometimes route over a split in a ground plane.
If a trace carries a DC signal, it should still be routed near a ground plane, but it is usually safe to route over a split in the ground plane
If the trace carries a high frequency signal, like the RF signal used in WiFi or Bluetooth, you should always route it over an unbroken ground plane and use copper pour around the trace.

Some applications, like high fidelity audio, equipment for sensitive analog measurements, and high voltage/high current power conversion systems require splitting ground planes into different regions, but traces are not normally routed between them in the manner shown above.

We’ll discuss more about why these routing practices are important in an upcoming lesson. These practices are implemented to prevent electromagnetic interference (EMI) and changes in trace impedance, both of which are important considerations for ensuring signal integrity.

Make Layer Transitions With Nearby Ground Vias

If you look at the above guideline, we didn’t talk about routing across multiple layers. If you route between two layers, how can you make sure you provide the nearby grounding you need to make sure you don’t have problems with EMI or signal integrity?

The standard way to do this is to make sure you place a grounded via that runs alongside the via that carries your signal in your PCB. If your signals need to have a ground plane on an adjacent layer, and you then need to route through a layer transition, then you should also place a ground via that runs close to the signal via.

In general, it’s best to keep the value of S close to the value of H as this will ensure the greatest noise suppression. The reason this is important in high speed signals is that it completes the circuit needed to send the signal to its destination component. We’ll discuss this more in a later section dedicated to high speed PCB design and routing.

For DC signals, you probably won’t need to do this unless you expect a lot of noise in your board. For AC signals, low-speed digital, and high-speed digital, it’s a good idea to do this just to ensure you’ve provided enough grounding near your signals and to suppress noise as much as possible. Failing to do this with high speed digital signals is a well-known source of EMI in a PCB, and it creates an area where EMI can be received in the board.

## [27] Simple Differential Pair Routing Example

The challenge with routing differential pairs is to ensure you maintain width and spacing throughout the length of the route. In the past, you would have to carefully route each side of the trace individually, which creates potential for mistakes along the length of the route. In modern ECAD software, you can use a specific routing tool for differential pairs, and the length/width/spacing requirements are enforced in your design rules.

We’ve shown a lot of guidelines needed to route traces around a board and ensure they will comply with the design rules in your project. Now we want to conclude this section by looking at a simple PCB layout and showing how to route some components with differential pairs and single-ended signals.

The video below should provide a good example of a strategy where we need to route both types of signals. In this example, we’ll perform the following tasks:

Setting up differential pairs in a schematic and in the PCB design rules
Routing traces between two components
Applying some length matching to the differential pairs

First, we’ll look at ensuring we’ve defined differential pairs in the schematic and what happens when these are not defined in your project data. The video below shows how you would access these tools with a simple example for routing between a BGA component and a connector.

Next, we need to apply some length matching to the differential pairs to ensure the signals arrive at their destination within some timing margin. Once you’ve finished routing the pair, you can use an automated length tuning tool to apply the length matching sections that were introduced in an earlier section of this course. The next video shows how to use the length tuning utility after initially routing a differential pair..

## [28] Routing Three Common Digital Buses

Many digital designs will use some common methods for sending, receiving, and reading digital data. Ever since semiconductor companies began developing highly specialized ASICs, they began working to help standardize and implement digital protocols for communication between digital components. Learning these signaling standards will help you quickly connect components in a new board, and hopefully you’ll have an ability to understand how these standards are used in some different embedded programs.

We’ll be looking at three common digital signaling standards in this lesson: serial peripheral interface (SPI), the inter-integrated circuit (I2C) protocol, and universal asynchronous receiver-transmitter (UART). These are moderate-speed digital protocols, but they can still experience some signal integrity problems in a design if they are not implemented correctly. Almost every microcontroller (including off-the-shelf boards like Arduino) will include these protocols.

Getting Started With Digital Signaling

Before going further, we have to ask the question: what exactly is a signaling standard or a digital protocol? A signaling defines a specific digital data format, number of wires, and data rate that components can use to communicate with each other. Some common signaling standards you might be familiar with are USB, HDMI, and Ethernet as these are used on almost every computer. Meanwhile, signaling standards like SPI, I2C, and UART are used between the chips placed on a circuit board, including in an advanced design like a smartphone or a laptop. They can also be used to route data between boards.

When you need to set up routing for any of these signaling standards for these components, you’ll need to think about the points in the table below. This table summarizes some of the important specifications that will be needed for routing these signaling standards:

	I2C	SPI	UART
Trace count	2 traces	At least 3 traces	2 traces
Data rate	Up to 3.4 Mbit/s	Up to 60 Mbit/s	Up to 1.5 Mbit/s
Impedance	N/A	N/A	N/A
Clocking	Source synchronous	Source synchronous	None
Routing topology	Serial bus	Serial bus	Serial bus, although theoretically you can do daisy chaining
Driver output impedance	Switches between low and high	Low	Low

Next, you might be wondering, which signaling standards should you use? This is not really the question we should be asking. When you’re selecting components, think more about the functionality you need, rather than thinking about picking specific signaling standards. Some functions, like needing to plug a device into a computer, will require USB. If you need to add a device to a local area network, then you’ll use Ethernet or possibly WiFi.

From our earlier discussions of high speed digital signals, you might be wondering whether any of these protocols would be considered “high speed”. The answer is: all of these could be considered high speed depending on the data rate and the component that uses the particular protocol. In general, even if you’re routing a digital interface that is not generally considered a high speed interface, it can still experience some of the same signal integrity problems as a high speed interface.

## [29] I2C Routing

I2C uses bus routing with 2 wires as shown in the image below. These two signals are named SCK (clock line) and SDA (data and address line). The protocol uses source-synchronous clocking, meaning the clock is routed on its own trace alongside the data trace (SDA).

The signals are routed from a single driver (master) component to multiple downstream peripheral components. The master device outputs a clock signal on the SCL line, and commands are sent to peripheral components on the SDA line. The SDA line is also used to send data back to the master controller.

There are two important specifications in the I2C standard:

Total current in the bus shall not exceed 3 mA
Low logic level is defined from 0 V to 0.4 V
The capacitance of all traces and inputs on the peripherals shall not exceed 400 pF at the highest data rate of 3.4 Mbit/s
The I2C specification requires at least 1 kOhm resistors on the SDA and SCK lines

The two resistors placed between the signal lines and the power bus are called pull-up resistors. Typical voltages used in I2C-capable components are at standard CMOS logic levels (5 V, 3.3 V, etc.). The resistors are selected such that the required current pulled into the master device from the power bus is limited below 3 mA for all devices. Your job is to determine the minimum resistor value for your power bus voltage with the following equation:

Typically, it’s safe to opt for a slightly higher resistor value so that the current sits just below 3 mA. This provides an added benefit of slightly increasing the rise time of the data and clock signals so that there will be less possibility of interference with other signals.

Now, we also have a rise time limit for the I2C bus. This is defined for the bus capacitance:

I2C pull-up resistor value maximum and minimum values:

Note that the number in the denominator above is defined for a 30% to 70% transition time. For a 10%-90% transition time, replace 0.8473 with 2.2. This will further limit the value of the pull-up resistors.

The other limiting factor that will determine the total amount of conductor you can use in an I2C bus is the bus capacitance. This means that you cannot make the traces too wide or too long, and the input capacitance on the peripherals should not be too high. Each device will typically contribute on the order of 10 pF of capacitance to the bus. Short routes with ~10 mil traces are sufficient for most designs, and a conservative rule of thumb is to have no longer than 10 cm routes. Note that the connections in the above image show a trace branching off to other components; this is what you would do when routing the bus.

Just as an example of how long these buses can get, take a look at the image below. In this image, the SCL trace is being routed from an MCU near the center of the board and out to two peripherals. The SCL trace is highlighted in white. This trace spans all the way across the bottom side of the board, and it makes multiple layer transitions on the way to its destination.

It’s often said that it’s hard to mess up I2C and other serial bus interfaces that run at low speed. In some sense, this is true; the edge rate on the bus is low enough that most boards will be smaller than the critical length for I2C signals, so routing is much easier than with a higher speed computing peripheral like USB or DDR.

If we zoom into the right side of this board where the trace branches, we can see where the routing splits off to the two peripherals along this route. We can also see where the pull-up resistors are placed along the SCL and SDA lines back to the +3V3 power bus. These are outlined in yellow in the image below.

In this example layout, Peripheral 1 is a connector, which is shown in the image below. The SCL and SDA lines are being routed to a 4-pin header, as shown below. If you look along this line in the above image, you’ll see a 3-pin component that bridges the SDA and SCL lines. This component is a TVS diode and it is used to protect other components connected to the I2C bus from electrostatic discharge that might damage an integrated circuit.

It’s quite common to place TVS diodes or other ESD protection circuits on I2C or other serial buses if there is some danger of ESD occuring. When conductors on a connector are exposed, they are at risk of receiving an ESD pulse that can damage components. Placing a TVS diode in this way helps protect components from static electrical discharges. Keep this in mind if you are routing an I2C bus or other bus to a peripheral device.

## [30] SPI Routing

SPI uses at least 3 connections between components. This protocol also uses a source-synchronous clock with power supplied at logic levels. The pin names are given as follows:

SDO: Serial data out
SDI: Serial data in
SCK: Serial clock
CS: Chip select

There are deprecated signal names on older devices. These are MISO (master-in slave-out, equivalent to SDI), MOSI (master-out slave-in, equivalent to SDO), and SS (slave select, equivalent to CS). The reason for the change was to eliminate confusion among devices that could function as either a controller or peripheral. An example implementation with a single controller and two peripherals is shown below.

CS Pins

A CS pin is used to toggle specific peripherals so they turn on or off as required during a data frame. Components that use SPI may have more than one CS pin as shown above, so that multiple peripherals can be activated as needed. When serial data is output from the controller, the required peripheral also needs to be activated by the controller during a data frame so that the peripheral will accept and read the data. This is programmed in the controller’s logic. For example, if a microcontroller or FPGA is used as the controller, it will be implemented in the code for the device’s application.

You could also have a totally different circuit that controls the CS pins on the peripherals. There is no requirement that the CS pins on peripherals be toggled by the controller. As long as the logic level that is output from an external circuit matches the logic level used in the peripheral, then there should be no problem using this external circuit to toggle the CS pins on the peripherals.

Routing

The routing method in SPI is similar to what is done in I2C as shown above. SPI routing is very forgiving and it can be implemented with layer transitions through vias as needed. Because the input and output logic circuits in SPI are push-pull CMOS buffers, they do not require pull-up resistors at the source and receive ends like we would have in the above diagrams for I2C. SPI also does not have a controlled impedance requirement specified in the SPI standard.

In the case where lines are very long and termination is needed, the following would need to be implemented:

A small series termination resistor (about 22 Ohms) at the beginning of the traces
Traces designed to a specific impedance (usually 50 Ohms)
A small resistor equal to the trace impedance connected in parallel to GND at the end of the traces

Once these points are taken into account, simply route the traces in a bus topology as you would do for I2C by branching connections off of the main bus line over to the destination component.

## [31] UART Routing

UART uses a 2-wire link to connect one controller and one peripheral. The two traces are single-ended and should be routed with a shared ground connection as shown below. This ensures that a logic level signal (5 V or 3.3 V) that is sourced from the controller will be read as the same voltage level at the peripheral.

As this is a single-ended bus, there is no need to route these side-by-side as you would a differential pair. The controller side and the peripheral side of a UART link are asynchronous, meaning they do not require a clock signal for synchronization. This is handled internally in the controller and peripheral IC. The resulting routing is very simple and only requires traces routed directly between the two components.

UART also does not have an impedance requirement, and it can be implemented over long traces or cables. Eventually, it can experience the same transmission line effects as faster digital interfaces, just as is the case with I2C and SPI. You will need to check the specifications of your driving component to ensure the signal rise time is not too short that you would need to implement impedance.

## [32] Possibility of High Speed Behavior in These Buses

When routes become very long, the buses might start to exhibit high speed behavior that is typical in a faster digital protocol like USB, DDR, or even faster buses. In such cases, make sure to set the trace width to the right value by assigning a design rule to each of the data lines in the particular interface. You can also just set the trace width to the value needed for a target impedance during routing. Make sure to review the previous lessons to see how to set these design rules or set trace widths as you route.

Once traces become very long such that they need specific impedance, then you have a long parallel bus. In this case, it’s a good idea to match the lengths of the traces. At short trace lengths, there is not a strict requirement and the traces do not need to be routed side-by-side.

On the vast majority of boards, the need for any kind of length matching and impedance control will not be necessary. These interfaces are normally implemented in smaller boards with very direct routing between two or more chips, and the rise time is generally low enough that any problems with reflections due to lack of controlled impedance are less likely to occur. As an example, designing to a controlled impedance is important in two practical situations:

When routing data lines between two boards over a very long cable
When routing across a large board through multiple connectors, such as a backplane and its daughterboards

A more important problem is crosstalk, which can occur regardless of the length of your traces. The main way to help suppress crosstalk is to apply sufficient spacing between traces carrying digital data, as well as to route traces over a ground plane. Just because these digital interfaces are not running at the fastest edge rates doesn’t mean you should neglect the ground plane requirements. If you’re building a real product, it’s highly advisable to route these interfaces near a ground plane to take advantage of its natural shielding.

In summary, we looked at three popular moderate-speed buses that are used in many embedded systems. In the next unit, we’ll look deeper at what qualifies digital signals in a design as “high speed” and quantify this in terms of rise time.

## [33] What Makes a Design "High Speed"?

High speed PCB design is one of those topics that is now at the forefront of electronics design and layout. In the past, high speed PCB design was something unique, and the tasks involved in creating a high speed PCB weren’t used in many other systems. Today, most designs that include digital components and circuits would be considered to operate at high speeds. This means that these components and circuits are prone to signal integrity problems if layout and placement are not done properly.

The first thing to understand about high speed design and high speed signals is that there is one important parameter that governs signal integrity: the signal’s rise time. This value will determine when termination is needed on PCB traces, how a signal can induce crosstalk in a design, and more advanced signal integrity problems that are beyond the scope of this course.

## [34] Clock Rate vs. Signal Rise and Fall Times

Perhaps one of the greatest misconceptions about high speed PCB design and high speed digital signals is that the term “high speed” refers to the clock rate in a digital component or in a signaling standard. This is incorrect. As we saw in the previous lesson, there are some signaling standards that do not use clocks (UART), but these can still experience signal integrity problems when a component switches logic states. A high speed PCB uses digital signals with fast transition times (rise time or fall time between logic states), regardless of the clock rate. While it is true that a faster clock requires that a signal have a faster rise time, the reverse is not always true. A design could have a very low clock rate, yet the edge transitions on the clock signal and on the digital signals in the design can still be very fast.

Visualizing Rise Time

To see how rise time and fall time in a digital signal are important, we first need to look at a typical graph of the waveform for a digital signal. The graph below shows an example waveform for a repeating digital signal. On each edge, the signal transition looks ideally like a discharging RC circuit. Here, we’ve zoomed into a single repetition between the LOW and HIGH states (0 V and 3.3 V, respectively).

This waveform has a rise time and fall time of approximately 5 ns (measured from the 10% level to the 90% level). A 5 ns rise time is typical for many digital components that are used in a modern PCB layout. This value is limited by the output capacitance of the transistors used in logic circuits for the particular component. If the above digital signal were a repeating clock signal, we can immediately see that the clock period is 60 ns, equating to a clock frequency of 16.67 MHz.

Clearly, we could make the clock period much longer, meaning the clock frequency would be lower, it is still possible to have the rise time remain very fast with a slower clock. The opposite is not always true. If, in the above graph, the clock frequency were 1 GHz, then the clock period would be 1 ns. Obviously, the clock period cannot be 1 ns with a 5 ns rise time; the rise time would eventually have to decrease as the clock period decreases.

High Speed Interfaces and Data Rate

In the above image, a 5 ns rise time was used as an example, but this is a typical value that is found in many digital integrated circuits. Components with rise times on the order of 10 ns will start to exhibit noticeable signal integrity problems, and they can only get worse with a faster rise time. There are only a few strategies that can be used to solve signal integrity problems, and we’ll discuss some of these in this section.

Regardless of the above point about rise time/fall time, there are some digital interfaces that are generally considered “high speed” due to their high data rates. Just like a fast clock tends to have a fast rise time, a bit stream with a high data rate also tends to have fast rise/fall times along the edges of its digital signals. Some of the popular digital interfaces used in modern PCBs are shown in the table below.

Low speed (Less than ~100 Mbps)	High speed
SPI
UART
I2C
I2S
CAN bus
Ethernet (10Base and 100Base)	USB (Universal serial bus)
LVDS (Low-voltage differential signaling)
HDMI (High-definition multimedia interface)
MIPI protocols (CSI, DSI, etc.)
Ethernet (1G and higher)
DDR (Double data rate)
PCIe (Peripheral component interface express)
SATA (Serial advanced technology attachment)

In looking at the above table, just remember the following point: just because a digital interface is not considered to be high speed, it doesn’t mean that interface will be free of signal integrity problems.

At this point in our discussion of rise time and high speed digital signals, we want to consider two important signal integrity problems:

The need for impedance matching when a trace is long
Crosstalk between traces

## [35] Impedance Matching

Impedance matching, also called termination, is the practice of setting all portions of an interconnect to the same impedance. In the previous lesson, it was mentioned that termination might be required when a trace is very long. Why should this be the case, even when using something like I2C, which might not use signals with fast rise time?

Short Traces

To determine whether you need termination, you need to compare the length of the line to the distance a signal travels during its transition. To see why this is important, take a look at the example diagram below. In this example, the rise time is slow enough such that the signal can travel along the entire length of the trace as it makes it transition to its HIGH logic level.

In the above image, the signal spans across the entire length of the interconnect while it is rising up to its final voltage. Remember, signals that travel along a trace are electromagnetic waves, so they travel at the speed of light. So, if v is the speed of light and T is the rise time, the signal occupies a trace length of L = vT as it rises to full strength. The same idea applies to the fall time.

As an example, if we use Dk = 4 for the dielectric constant of an FR4 substrate, then the speed of light will be (300,000,000 m/s)/(√4) = 150,000,000 m/s. If the signal rise time is 5 ns, then the signal will travel 0.75 m, or 750 mm during the period where the signal is rising.

If the trace length is much shorter than this value, then we don’t need to worry about the impedance of the trace. This is because, from the perspective of the load component in the above example, the signal looks like and behaves like a slowly-rising DC voltage. From the signal’s perspective, the component begins reacting to the signal at the very instant electromagnetic power is distributed across the interconnect. This means that the signal behavior is dominated by the load’s impedance and not the trace’s impedance.

Long Traces

Now consider what happens when the rise time is much faster. In the image below, the signal rises to its final value very quickly, long before it reaches the end of the trace. After rising to its full signal level, the signal can then propagate to the load component.

Let’s suppose that, in our example with a PCB laminate of Dk = 4, we instead have a signal with a 0.25 ns rise time. In this case, the signal will travel a distance of 0.0375 m during its transition, or a distance of 3.75 cm. If the trace is much longer than this value, then the trace will need to be designed to a specific impedance value (usually 50 Ohms, or 100 Ohms for a differential pair).

In the above image, the signal transition is so fast that the signal only interacts with the trace during its rising and falling transitions. It has no interaction with the load during these times, and the entire signal must travel down to the end of the trace before there can be any interaction with the load. Because of this, the signal is only interacting with the trace, and so we need to make sure the trace impedance has the right value

Impedance Matching

It was mentioned in the previous lesson that impedance matching is important. This term refers to the practice of setting sure the source, trace, and load impedances to the same value. For a basic CMOS logic circuits, the source output and load input logic circuits do not have the same impedances:

CMOS input buffers: Input impedance at a load logic component is high (on the order of 1 MOhm)
CMOS output buffers: Output impedance between a source logic component and a trace is low (on the order of 0.1 Ohms)
Traces: typically designed to 50 Ohms in most high-speed signaling standards (see the above table for a list)

Obviously, we have an impedance mismatch. The general scheme for applying impedance matching is to add resistors at the source and load ends of a trace as shown below.

This image shows the typical impedances at the input and output ports of a source and load. Impedance matching is applied for a low-impedance source by placing a series resistor. At load end, impedance matching is applied with a parallel resistor to GND.

Note that components designed to common high speed signaling standards will use on-die termination. This just means that the terminating resistors shown in the above circuit diagram are applied on the semiconductor die; they do not need to be placed external to the component unless specified in a component datasheet. Some components (for example, DDR RAM modules) can have selectable on-die termination, where the input and output impedances are selected from a set of values using a configuration resistor or are sensed automatically.

For something like SPI or I2C, as we mentioned in the previous lesson, termination would need to be applied manually, but only in the case where the traces are very long.

## [36] Rise Time and Crosstalk

If you recall your electronics 101 or physics 101 classes, then you know that certain electrical and magnetic behavior will occur when an electrical signal (either current or voltage) switches states. Whenever a signal switches, causing the voltage to switch between states and current to flow on a PCB trace, the transition generates an electromagnetic pulse. The electric and magnetic portions of the field can interact with other traces, and the strength of this interaction depends on the rise time of the signal.

Inductive coupling is mediated by the magnetic field and dominates at lower frequencies. When a digital signal changes, the changing current generates a changing magnetic field, which can induce crosstalk in a nearby trace.

Capacitive coupling is mediated by a changing electric field and dominates at very high frequencies. This is much more important in advanced RF products, such as radar boards and 5G systems. In most PCBs, inductive coupling will be dominant at lower frequencies.

These two mechanisms are responsible for crosstalk between two traces in a PCB. If two traces are placed too close together, the signal on one trace can induce a signal on a neighboring trace during its rising edge. The graph below shows a simulation result that illustrates this behavior. The trace carrying the signal that creates crosstalk is called the aggressor, and the trace that receives the resulting crosstalk signal is called the victim trace.

When the rising edge is faster, the amplitude of the signal induced in the neighboring trace will be larger. There are three possible strategies to reduce or eliminate crosstalk due to induction:

Place a small series resistor on the output of the signal source to slow down the rise time. This is a less-desirable remedy as it will reduce the signal level that reaches the receiver component.
If traces are being routed on adjacent layers, only route them in perpendicular directions on each layer. Traces routed in parallel can more easily exchange energy as crosstalk.
Crosstalk depends on the trace width to substrate thickness ratio (w/h, see the image below). Make sure to route over a ground plane, and use a larger w/h ratio.

By far, the most effective method for reducing crosstalk is to use a ground plane and a thinner dielectric. The w/h ratio affects both the impedance of a trace and the amount of crosstalk a trace can generate/receive.

Crosstalk through capacitive coupling is more difficult and is something of an advanced topic in PCB design. For most traces and signals you’ll work with, you will care more about the inductive portion of crosstalk as this will affect a wide range of circuits. The capacitive portion is particularly problematic in RF signals running at GHz frequencies (such as wireless products), as well as in very high speed digital signals running at multiple Gbit/s data rates.

Inductive crosstalk doesn’t just occur between traces; other circuits and components can generate strong crosstalk that can be received by traces carrying digital signals. The opposite occurs as well; digital signals can induce crosstalk in other circuits or traces that are not carrying digital signals. As an example, switching regulators can generate strong noise at frequencies ranging from about 100 kHz up to 10’s of MHz. This is definitely within the frequency range where inductive crosstalk is dominant and can interfere with digital signals.

## [37] Summary

In this lesson, we’ve looked at two of the most basic signal integrity problems that can occur in a design. There is a third important signal integrity problem that can occur when traces are not routed properly: EMI. This problem was omitted from this section because it relates to grounding and stackup design in a PCB. In the next section, we’ll look more at this additional aspect of stackup design, routing, and signal integrity.

## [38] Electromagnetic Interference (EMI)

Most courses and textbooks on electronics design would not take time to introduce the core concepts in routing and grounding alongside topics like electromagnetic interference (EMI). However, in PCB design, these conceptual areas are deeply related, and several design problems that generate excessive EMI are related to grounding and routing in a PCB. In today’s modern electronics, even simple designs like microcontrollers can experience EMI challenges due to the use of fast edge rates in digital logic.

We’ve mentioned multiple times in earlier lessons, and in various contexts, that there are some basic routing rules to follow when working with digital signals, and particularly with high speed signals. While we’ve focused on impedance and crosstalk in the previous lesson, we haven’t focused on the broader area of EMI. If you think about it, crosstalk is really a basic form of EMI; it is unwanted noise that is coupled into one of your circuits. Generally, the term “EMI” is broad enough to include noise induced from any source (internal or external to the board). This section will look more at EMI, particularly as it relates to routing and stackup design.

Why EMI is Important

Why do we need to worry about noise and EMI? The overarching answer is simple: it’s required by law. The majority of countries in the developed world have developed regulations that set limits on EMI generated by electronics, as well as PCBs under test and complete PCBAs. If a new product is to be released for sale on the open market, it must pass electromagnetic compatibility (EMC) testing requirements within that particular jurisdiction. These tests are used to measure how much radiation a device emits, conducts, or receives from an external source. EMI comes in two forms: radiated and conducted.

## [39] Radiated EMI

Radiated EMI originates as a time-varying electromagnetic field. Essentially, one device emits some radio frequency energy, and this energy is received by another device and interpreted as noise. All electronic devices will emit some radiation; your job as a circuit board designer is to create a PCB layout that minimizes radiated EMI. An example measurement of noise emitted by a small digital device is shown below.

The red line shows radiated emissions limits specified in a European industry standard. The blue lines show radiated emissions measurements at each frequency. If you wanted, you could gather measurements and create a similar curve at a range of frequencies with a low-cost oscilloscope and some signal processing steps in a program like Mathematica, MATLAB, or even Python.

The only type of electronic device that does not emit radiated EMI is a device running at a DC voltage and current. However, if you’re familiar with power conversion and power regulator circuits, then you’ll know that real DC devices will use switching signals or will contain AC signals that emit some noise. This means even a simple DC device can produce radiated EMI, and it can still receive some radiated EMI from an external source.

Radiated EMI Compliance

In the US, the Federal Communications Commission (FCC) is responsible for regulating emissions from electronic devices. Similar regulations have been adopted in Europe and are specified under the CISPR (Comité International Spécial des Perturbations Radioélectriques) standards; there are different sets of standards for different products. Other sets of standards are specified in Australia, Japan, and other countries. The FCC emissions limits are specified for two types of devices:

Intentional radiators: These devices include anything with a wireless protocol. They should only emit strongly in their specific wireless communication bands. Radiation should be suppressed in all other frequency ranges.
Unintentional radiators: These are not designed to emit radiation in any frequency range. FCC guidelines define two types of digital devices: Class A and Class B. Generally speaking, Class A devices are intended for industrial environments, while Class B devices are intended for residential use.

If you’re planning to take a product to market, you won’t be sending it into government agencies. There are private laboratories that can provide testing services for a fee. Before releasing the product to market, it’s best to have a lab perform EMC testing before scaling up to high volume.

## [40] Conducted EMI

Conducted EMI is more important in power systems, as well as in devices that must communicate data or provide power over cables. Conducted EMI refers to currents that travel from one device and into another over a cable, or between circuits over traces on a PCB. Conducted EMI can originate as radiated EMI, meaning a radio energy source creates noise in your board, and that noise can conduct to other circuits. Similarly, conducted EMI can produce radiated EMI, which is what occurs when a switching signal generates a current on your PCB.

There are two types of conducted EMI: common-mode noise and differential-mode noise. Common-mode noise is the type of noise that you need to worry about because the radiation it produces can be ~100x more intense than radiation from differential-mode noise. The diagram below shows how each type of current flows in a PCB. When equal-magnitude, same-direction currents flow on two conductors, this is a common-mode current and it produces common-mode radiation.

In this image, we have a signal traveling between a source and a load. If some noise is present on the conductors that carry the signal current, it can travel as common-mode noise. The common-mode noise in this example has same direction and same magnitude on both conductors.

Conducted EMI Compliance

In addition to radiated EMI, the FCC, CISPR, and other regulatory bodies or standards place limits on conducted EMI. The goal is to limit unintentional noise transfer between devices connected to the same power circuit, or with a data cable, below some limits. Just like radiated EMI, a device will need to pass conducted EMI testing from a certified facility before it can be sold commercially. Devices will also have to pass electrostatic discharge (ESD) testing to ensure safety and reliability before being sold.

Conducted emissions in a PCB layout are calculated using a specialized application called an electromagnetic field solver is used. Some ECAD applications have a 2D version of a field solver built into their stackup and routing tools; this is how Altium Designer calculates impedance. These solver applications will generate results like those shown below, where the current density in the ground and power planes are shown using a color scale (red is highest, blue is lowest near zero).

This image shows that a strong current has been induced on a line reaching a connector, and this current will conduct through a connection on the top-left edge of the board. Any cable that is connected to the white connector can receive this noise and conduct it to some other electronic device.

When unwanted noise is conducted through an interconnect, its frequency content is compared with limits specified in some regulatory standard. This noise will be a mix of many frequencies, but the power carried in each noise can be measured with a spectrum analyzer, or it can be calculated in a simulation. The graph below shows such a simulation result; the red curve shows the amount of power carried in various frequency components that make up the noise signal, and the gray line shows a particular frequency limit as specified in the CISPR 25:2008 standards for European products.

These results were generated using Ansys HFSS, a popular field solver application that can be used to run simulations on PCB layouts created in Altium Designer. At the end of this lesson, you’ll find a link where you can access free courses to learn about using Ansys simulation tools.﻿

Electrostatic Discharge

One potentially dangerous type of conducted EMI is ESD. When an ESD event occurs, a large current pulse can be induced in your circuits or components. As a result, some components can be damaged or destroyed. This occurs through the same mechanism as a lightning strike, so a spark is often seen when ESD occurs near your design.

This can occur whenever your design has some exposed conductors through the enclosure without a low impedance path to ground. The term “exposed conductor” could refer to any ungrounded metal on the PCB, but it most often refers to shrouded connectors. If too much static charge accumulates on these pieces of exposed metal, the user can be shocked when interacting with the component, or an ESD current can travel into a nearby circuit. For this reason, it’s important to connect these exposed conductors to ground if possible.

These USB Type B and Type C connectors can be a location where ESD occurs. This is solved by grounding the components to the ground plane or to any metal in the enclosure.

Generally, we would prefer to connect exposed conductors (like the shroud of a connector, see above) to the chassis, which should be connected to earth. If this is not possible, it should be connected to the ground plane so that any current received in the conductor will be immediately sent to ground, rather than to your components and circuits.

Make sure to read about the basic types of ESD protection circuits in one of the links in the references section. If your design will be used in an environment where ESD might occur, then ESD protection circuits should be used in the design.

## [41] Devices Shouldn’t Interfere

The main reason we care about EMI and testing for EMC is that we would naturally want to prevent two electronic products from interfering if they are brought near each other. Imagine if you placed two smartphones on a table next to each other. You should naturally expect both phones to work properly, even though each phone might emit some noise that could interfere with the other phone (or any other electronic product). Similarly, if you connect two devices together with a data cable, we wouldn’t want strong noise to conduct between the two devices.

These problems are solved from three dimensions:

Board layout: The PCB design guidelines presented in this course, specifically around grounding and routing, are intended to help suppress EMI from your PCB and help ensure you can pass compliance tests.
Stackup design: Most EMI problems are solved by redesigning the PCB stackup, or by applying the proper level of grounding in the design. Sometimes, bridging connections to the same ground will solve emissions or conduction problems.
Filtering: This is a basic strategy for reducing conducted EMI. Filtering involves strategically placing filter circuits so that conducted noise is suppressed or sent to ground. The exact type of filter to be used depends on the use case of the product and any potential EMI that can arise in it's typical environment.
Enclosure design: Many enclosure designs could use metal or may leave small gaps for radiation to enter the system. Grounding the enclosure, the board, and exposed conductors will help reduce or prevent EMI.
ESD protection: Designs that might experience some ESD should include connections to ground so that any discharged current does not damage any of the components in the PCB. There are several ESD protection circuits presented in the reference at the end of this lesson.

## [42] Suppressing EMI

You can never totally remove EMI from any design, there will always be some noise that exists in your design and that is emitted from the PCBA and enclosure. However, some of the guidelines below will help reduce the amount of noise received from an external source, as well as the amount of noise your design might create as radiated or conducted EMI.

Ground Planes for Routing

Using ground planes below and/or above routing layers, as we’ve described in other lessons in this unit, is the best way to help suppress EMI. You should do this even if you don’t need to have impedance controlled traces in your PCB layout; the ground plane will provide some shielding against external EMI and will help suppress crosstalk (review Lesson 7 in this unit for more on crosstalk).

In addition, don’t use a split ground plane unless absolutely necessary. Even if you do need to place a split ground plane, don’t route traces over the ground plane. There are a few uncommon instances where it is okay to split up ground planes:

Galvanic isolation in power systems as this helps prevent dangerous currents from reaching the user
Some audio systems, simply because the frequencies involved are so low that it is difficult to control return currents
Other low frequency analog systems operating in the audio frequency range
Transformer-coupled routing (Ethernet, for example), where a transformer is used to send signals into a cable or transmission line
Routing

Proper routing will help prevent many common EMI problems. This includes routing over an adjacent ground plane and enforcing impedance rules where applicable. In addition, because traces are often routed in groups, it’s important to consider spacing between traces as that is the most effective way to prevent crosstalk. Make sure to review the routing guidelines earlier in this unit as these guidelines will help suppress radiated EMI, as well as prevent susceptibility to radiated EMI from an external source.

Conducted EMI at Power Inputs and Outputs

The idea behind using these components or circuits is to remove conducted EMI that comes into a design from the power supply or from the electrical grid. Similarly, these could be used on the output from a power supply or a power regulator circuit, although they are more effective when placed on the input.

Ferrite choke: These components are placed around the outside of a power cord. They are used to filter both common-mode and differential-mode noise. Do not use ferrite components on the output from a DC power regulator.
Common-mode choke coil: This pair of inductors uses opposite-turn coils, so current in one will cancel current in the other coil. These are designed for common-mode noise or differential mode noise; they can’t remove both types of noise simultaneously.
LC filter circuit: These circuits are designed as low-pass filters that allow common-mode or differential-mode noise to pass to ground instead of passing into your circuits and components.

Common-mode choke coils are commonly used in power systems to remove conducted common-mode noise.

Grounding Metal in the Enclosure

In general, if the enclosure for your board contains metal, it’s best to set it to the same ground as the ground level on your input power. How exactly this is done is a complex topic. The point is, large bits of metal like your enclosure (or a heat sink on a large IC) should not be left floating and should be grounded.

In the simplest type of design, you will be using an isolated 2-wire DC power supply or a battery to provide power to your board. In this case, the easiest method for grounding is to place a mounting hole near the power input that is connected to the enclosure. If there is an earth connection, the typical method is to leave your board’s ground plane disconnected from earth, and instead connect the enclosure and mounting hole to earth.

The enclosure in your PCB design can be a place to drop high frequency noise. Some circuits may receive high frequency noise from an external source, even if the enclosure is metalized and is grounded. Noise can also be transferred between different regions of the board as crosstalk, but a low impedance path to ground can be created through one of the mounting holes. However, for safety, you don’t want your enclosure (chassis) to be a current carrying conductor; this creates an electrocution risk for the user, especially when operating at high current.

The image below shows how common mode noise can arise through your enclosure. This occurs because there is some capacitance between the grounds in your PCB and any metal on the enclosure. When this capacitance is very large, high frequency noise can move around the PCB and into the enclosure, forming a large loop of common-mode current. The path followed by common-mode current (ICM) is marked with purple arrows.

## [43] Summary

Sometimes, being able to spot EMI problems takes experience. Designing for EMC is both an art and a science, and many lessons can be learned by correcting a design that happened to fail an EMC test. Now that we’ve covered some of the important aspects of EMI, you should have all of the basic knowledge needed to take more advanced courses in PCB layout. All the guidelines shown in this unit are intended to give you the background knowledge needed to layout most designs, as well as prepare you for more advanced courses on EMI/EMC, PCB layout, and signal integrity.
