# AD20 Essentials - Module 12: Updating the PCB

> Source: `ad20-essentials-exercises.pdf` (same folder), PDF pages 126-127 (printed page = PDF page; `<!-- p.N -->` marks page starts). Text only: figures are not extracted, only their captions. Altium Designer 20 UI; menu and panel names can differ slightly in newer versions.

<!-- p.126 -->

## 12.1 Purpose

In this exercise, you will learn about component links and how it is used to
synchronize the schematic components to the PCB document.
In order to synchronize schematic components to a PCB document within a project, each component
contains a unique identifier which is used to link them together. If no link is defined or if the link is
broken, the synchronization will fall back to the Component Designator. Matching the Component
Links is crucial part to keeping your design synchronized at all times.

## 12.2 Preparation

1. Close all open projects.
2. For this exercise, we will be using the WCTopping.PrjPcb project located in the AD20
Essentials Exercises\ Module 12 - Updating the PCB folder.
3. Open the WCTopping.PrjPcb project in Altium Designer.
4. Open and focus on the WCTopping.PcbDoc. Notice all components placed outside of the
board towards the right.

## 12.3 Component Links

5. Go to Design » Import Changes from WCTopping.PrjPcb. Notice that there are
unmatched components as shown in Figure 151 below. This can be easily resolved by
clicking Automatically Create Component Links. However, this exercise will detail how it
can be done manually.
6. Click Cancel and then close the Engineering Change Order window that pops up.

*Figure 151. Component Links error dialog*
7. Go to Project » Component Links… . Choosing “Manual Component Links” Step 5 would
have loaded the same dialog.
8. Notice the unmatched components in the first two columns as shown in Figure 152 below.

<!-- p.127 -->
9. Ensure that the Designator checkbox is ticked, then click Add Pairs Matched By ». This will
match the schematic symbol with the PCB footprint for each component, based on their
designator.

*Figure 152. Component Link Setup*
10. Click Perform Update. Notice the Information window as shown in Figure 153 below,
indicating that 59 links have been modified. Click OK.

*Figure 153. Component Links information dialog*
11. To ensure all components are synchronized, run the Design » Import Changes from
WCTopping.PrjPcb, if the design is synchronized and up to date you will see the dialog
below (Figure 154). If any difference is detected it will be shown in an ECO dialog.

*Figure 154. No differences detected, meaning that your Component Links are synchronized*
