# Modeling and Simulation

**Smart Indoor Lighting Control System · DIALux + Honeybee/Radiance**

This section documents the modeling and simulation workflow used to support the design, analysis, and control of the smart indoor lighting platform. The work combines **electric-light simulation**, **daylight simulation**, **sensor-based prediction**, **gain-matrix analysis**, and **zone-based control modeling**.

## Overview

The simulation and analysis framework was developed to answer several engineering questions:

- How should the luminaires be arranged in the office space?
- What illuminance distribution and uniformity can be achieved?
- How does daylight vary over time and across the floor plan?
- How can a limited number of sensors estimate the uncontrolled daylight condition in the whole space?
- How can panel contributions, lux-per-watt effectiveness, and zone relationships be quantified for optimization and control?

The overall workflow combines:

- **DIALux** for electric-light layout, lighting performance assessment, and spatial evaluation.
- **Honeybee/Radiance** for daylight simulation and time-varying illuminance analysis.
- **Mathematical analysis** for reduced-sensor prediction, zoning, gain-matrix interpretation, and sensor-placement studies.

## DIALux electric-light modeling

DIALux was used to construct the room geometry, partitions, windows, work areas, and luminaire layout. It was mainly used to study:

- spatial arrangement of lighting panels,
- electric-light illuminance levels,
- zone coverage,
- uniformity and distribution quality,
- and the relationship between panel placement and target work-plane performance.

### DIALux 3D overview

![DIALux 3D overview](images/dialux_3d_overview.png)

### Plan view, zoning, and illuminance evaluation

![DIALux plan and zoning](images/dialux_plan_uniformity_zones.png)

These simulations supported layout decisions and helped evaluate whether the luminaire arrangement could satisfy practical lighting requirements before and during experimental implementation.

## Honeybee / Radiance daylight modeling

Honeybee/Radiance was used for daylight simulation in the same office environment. The daylight model was used to estimate the **uncontrolled illuminance** contribution from windows and ambient daylight at different times of day.

The simulation workflow was used for:

- daylight maps over the floor plan,
- time-dependent daylight behavior,
- comparison between different sensor locations,
- and development of reduced-sensor prediction methods.

### Interior daylight render

![Radiance interior render](images/radiance_interior_render.jpg)

### Example daylight maps across different hours

![Daylight maps](images/daylight_maps_reference_sensors.png)

### Virtual-sensor grid daylight maps

![Virtual sensor grid maps](images/virtual_sensor_grid_maps.png)

## Daylight prediction and reduced sensing

One important goal of the project was to predict daylight conditions in the whole environment using only a limited number of real sensors.

For this purpose:

- virtual illuminance points were studied across the office plan,
- daylight behavior was observed over representative hours and days,
- mathematical relationships between reference points and the remaining zones were analyzed,
- and reduced-sensor prediction logic was developed for controller integration.

This work supported the estimation of zone illuminance using a smaller set of strategically placed sensors instead of dense physical measurement coverage.

### Time-varying illuminance profiles of virtual points

![Virtual sensor daily profiles](images/virtual_sensor_daily_profiles.png)

## Gain matrix, lamp contribution coefficients, and lux-per-watt analysis

The modeling and analysis framework was also connected to the control and calibration stages.

The system uses panel–sensor relationships to quantify how each lighting panel contributes to each sensing point or zone. This contributes to:

- **gain matrix construction**,
- **lamp coefficient interpretation**,
- **estimated panel contribution to each sensor**,
- **lux-per-watt effectiveness analysis**,
- and selection of the most efficient panels for each zone.

These quantities are later used by the controller and optimization modules to determine which panels should participate in each lighting task and how their duty levels should be selected.

## Zoning, uniformity, and control-oriented analysis

The office was divided into lighting zones to support occupancy-aware and energy-aware control. The modeling stage helped define:

- practical lighting zones,
- effective panels for each zone,
- expected coverage overlap,
- and uniformity-oriented analysis of panel arrangement.

This zoning information was later used in the dashboard and optimization workflow to map occupancy zones to sensor groups and panel groups.

## Optimum sensor placement and clustering-based reduction

Another major objective of the modeling work was to reduce the number of required physical sensors while preserving acceptable prediction quality.

To support this, the daylight simulation data was used for:

- comparison of many candidate virtual sensor positions,
- clustering of locations with similar daylight behavior,
- selection of representative sensing points,
- and mathematical analysis of minimum-sensor configurations.

This clustering-based view helps identify where a real sensor can best represent a broader region, reducing hardware complexity while maintaining useful environmental observability.

## Role in the full project

This modeling and simulation section forms the analytical foundation of the overall smart-lighting platform.

It supports:

- hardware design and panel layout,
- daylight-aware control,
- calibration and gain interpretation,
- optimization-based dimming,
- sensor reduction studies,
- and long-term development of scalable smart-lighting architectures.

For the corresponding hardware and controller implementation, see the [hardware documentation](../hardware/README.md), the [firmware section](../firmware/README.md), and the [central controller software](../software/README.md).
