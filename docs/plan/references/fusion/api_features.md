# Fusion API digest: features, extents, timeline, parameters, construction geometry

Generated like [api_sketch.md](api_sketch.md). Units are **cm** and **radians**. See [FUSION_REFERENCE.md](../FUSION_REFERENCE.md).

### ChamferCornerTypes
Specifies the type of corner to model when multiple edges come together at a vertex.
Values: ChamferCornerType=0, MiterCornerType=1, BlendCornertype=2

### CoilFeatureSectionPositions
List of the section positions of coil feature.
Values: InsideCoilFeatureSectionPosition=0, OnCenterCoilFeatureSectionPosition=1, OutsideCoilFeatureSectionPosition=2

### CoilFeatureSectionTypes
List of the section types of coil primitive feature.
Values: CircularCoilFeatureSectionType=0, SquareCoilFeatureSectionType=1, TriangularExternalCoilFeatureSectionType=2, TriangularInternalCoilFeatureSectionType=3

### CoilFeatureTypes
List of the coil types.
Values: RevolutionsAndHeightCoilFeatureType=0, RevolutionsAndPitchCoilFeatureType=1, HeightAndPitchCoilFeatureType=2, SpiralCoilFeatureType=3

### DraftFeatureTypes
** This class is a preview feature and may change in future releases.
Values: FixedPlaneDraftFeatureType=0, PartingLineDraftFeatureType=1

### ExtentDirections
List of the valid extent directions.
Values: PositiveExtentDirection=0, NegativeExtentDirection=1, SymmetricExtentDirection=2

### FeatureExtentTypes
Used to indicate which type of extent is used for a feature.
Values: OneSideFeatureExtentType=0, TwoSidesFeatureExtentType=1, SymmetricFeatureExtentType=2

### FeatureOperations
List of the different operations a feature can perform.
Values: JoinFeatureOperation=0, CutFeatureOperation=1, IntersectFeatureOperation=2, NewBodyFeatureOperation=3, NewComponentFeatureOperation=4

### FilletFeatureTypes
List of the fillet feature types.
Values: FilletFeatureType=0, RuleFilletFeatureType=1, FullRoundFilletFeatureType=2

### HoleEdgePositions
List of the valid edge positions for holes.
Values: EdgeStartPointPosition=0, EdgeMidPointPosition=1, EdgeEndPointPosition=2

### HoleTapTypes
List of the valid tap types for holes.
Values: SimpleHoleTapType=0, ClearanceHoleTapType=1, TappedHoleTapType=2, TaperTappedHoleTapType=3

### HoleTypes
List of the different types of holes.
Values: SimpleHoleType=0, CounterboreHoleType=1, CountersinkHoleType=2

### LoftedFlangeFacetControlTypes
** This class is a preview feature and may change in future releases.
Values: ChordToleranceLoftedFlangeFacetControlType=0, FacetAngleLoftedFlangeFacetControlType=1, FacetDistanceLoftedFlangeFacetControlType=2, FacetNumberLoftedFlangeFacetControlType=3

### LoftedFlangeFormingTypes
** This class is a preview feature and may change in future releases.
Values: BrakeFormLoftedFlangeFormingType=0, DieFormLoftedFlangeFormingType=1

### LoftEdgeAlignments
List of Loft Edge Alignment Options
Values: FreeEdgesLoftEdgeAlignment=0, AlignEdgesLoftEdgeAlignment=1, AlignToSurfaceLoftEdgeAlignment=2

### LoftRailEdgeConditions
Defines the different conditions that can be applied to a loft rail when the rail entity is defined by BRepEdge objects.
Values: G0LoftRailEdgeCondition=0, G1LoftRailEdgeCondition=1, G2LoftRailEdgeCondition=2

### OffsetCornerTypes
Specifies the different types of corners that can be created when offsetting a wire body.
Values: CircularOffsetCornerType=0, LinearOffsetCornerType=1, ExtendedOffsetCornerType=2

### OffsetTypes
List of Offset Types
Values: SharpOffsetType=0, RoundedOffsetType=1

### ParameterValueTypes
Specifies the different types of values that a parameter can be.
Values: NumericParameterValueType=0, TextParameterValueType=1

### PatternComputeOptions
List of the compute options for mirroring and patterning features in the parametric modeling environment.
Values: OptimizedPatternCompute=0, IdenticalPatternCompute=1, AdjustPatternCompute=2

### PatternDistanceType
Defines the different ways to specify the spacing between elements in a pattern.
Values: ExtentPatternDistanceType=0, SpacingPatternDistanceType=1

### PipeSectionTypes
List of the different section types of a Pipe.
Values: CircularPipeSectionType=0, SquarePipeSectionType=1, TriangularPipeSectionType=2

### RuledSurfaceCornerTypes
List of Ruled Surface corner types.
Values: RoundedRuledSurfaceCornerType=0, MiteredRuledSurfaceCornerType=1

### RuledSurfaceTypes
List of Ruled Surface Types.
Values: TangentRuledSurfaceType=0, NormalRuledSurfaceType=1, DirectionRuledSurfaceType=2

### ShellTypes
List of Shell Types
Values: SharpOffsetShellType=0, RoundedOffsetShellType=1

### SplitFaceSplitTypes
List of the ways to split a face using the split face feature.
Values: surfaceIntersectionSplitType=0, alongVectorSplitType=1, closestPointSplitType=2

### SweepExtentTypes
List of the types of sweep extent.
Values: PerpendicularToPathExtentType=0, FullExtentsExtentType=1

### SweepOrientationTypes
List of the types of sweep orientation.
Values: ParallelOrientationType=0, PerpendicularOrientationType=1

### SweepProfileScalingOptions
List of the sweep profile scaling options.
Values: SweepProfileScaleOption=0, SweepProfileStretchOption=1, SweepProfileNoScalingOption=2

### SweepSolidOrientationTypes
The various orientation types when doing a solid sweep.
Values: PerpendicularSolidOrientationType=0, RigidSolidOrientationType=1, AlignedSolidOrientationType=2

### ThickenTypes
List of Thicken Types
Values: SharpThickenType=0, RoundedThickenType=1

### ThinExtrudeWallLocation
List of Thin Extrude Wall Locations
Values: Side1=0, Center=1, Side2=2

### ThreadLocations
List of the positions of a thread feature when it is not full length.
Values: HighEndThreadLocation=0, LowEndThreadLocation=1

### BoundaryFillFeatureInput
This class defines the methods and properties that pertain to the definition of a BoundaryFillFeatureInput.
- `cancel() -> bool` — To determine the possible boundaries and allow you to choose which cells to keep, the boundary fill feature does a partial compute when the input object is created.
- prop `bRepCells`: BRepCells (ro) — Returns the collection of the valid cells that have been calculated based on the set of input tools.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the boundary fill feature.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the Boundary Fill is created based on geometry (e.g.
- prop `tools`: ObjectCollection (rw) — Gets and sets the collection of one or more construction planes and open or closed BRepBody objects that are used in calculating the possible closed boundaries.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `isRemoveTools`: bool (rw) — Gets and sets whether any BRepBodys that were used as tools should be removed as part of the feature creation.

### BoundaryFillFeatures
Collection that provides access to all of the existing boundary fill features in a component and supports the ability to create new boundary fill features.
- `item(index: int) -> BoundaryFillFeature` — Function that returns the specified boundary fill feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(tools: ObjectCollection, operation: FeatureOperations) -> BoundaryFillFeatureInput` — Creates a BoundaryFillFeatureInput object.
    - `tools`: A collection of one or more construction planes and open or closed BRepBody objects that will be used in calculating the possible closed boundaries.
    - `operation`: The operation type to perform.
- `add(input: BoundaryFillFeatureInput) -> BoundaryFillFeature` — Creates a new boundary fill feature.
    - `input`: A BoundaryFillFeatureInput object that defines the desired boundary fill feature.
- `itemByName(name: str) -> BoundaryFillFeature` — Function that returns the specified boundary fill feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of boundary fill features in the collection.

### ChamferEdgeSet
The base class for the classes that define the different types of chamfer edge sets.
- `deleteMe() -> bool` — Deletes the chamfer edge set from the chamfer.
- prop `isTangentChain`: bool (rw) — Gets and sets the Tangent chain for chamfer.

### ChamferEdgeSets
Collection that provides access to all of the existing chamfer edge sets associated with a chamfer feature.
- `item(index: int) -> ChamferEdgeSet` — Function that returns the specified chamfer edge set using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addEqualDistanceChamferEdgeSet(edges: ObjectCollection, distance: ValueInput, isTangentChain: bool) -> bool` — Adds a set of edges an equal distance offset to this chamfer feature.
    - `edges`: An ObjectCollection containing the edges to be chamfered.
    - `distance`: A ValueInput object that defines the distance offset of the chamfer.
    - `isTangentChain`: A boolean value for setting whether or not edges that are tangentially connected to the input edges (if any) will also be chamfered.
- `addTwoDistancesChamferEdgeSet(edges: ObjectCollection, distanceOne: ValueInput, distanceTwo: ValueInput, isFlipped: bool, isTangentChain: bool) -> bool` — Adds a set of edges an equal distance offset to this chamfer feature.
    - `edges`: An ObjectCollection containing the edges to be chamfered.
    - `distanceOne`: A ValueInput object that defines the first distance offset of the chamfer.
    - `distanceTwo`: A ValueInput object that defines the second distance offset of the chamfer.
    - `isFlipped`: Swaps the directions for distance one and two.
    - `isTangentChain`: A boolean value for setting whether or not edges that are tangentially connected to the input edges (if any) will also be chamfered.
- `addDistanceAndAngleChamferEdgeSet(edges: ObjectCollection, distance: ValueInput, angle: ValueInput, isFlipped: bool, isTangentChain: bool) -> bool` — Adds a set of edges an equal distance offset to this chamfer feature.
    - `edges`: An ObjectCollection containing the edges to be chamfered.
    - `distance`: A ValueInput object that defines the distance offset of the chamfer.
    - `angle`: A ValueInput object that defines the angle of the chamfer.
    - `isFlipped`: Swaps the directions for distance one and two.
    - `isTangentChain`: A boolean value for setting whether or not edges that are tangentially connected to the input edges (if any) will also be chamfered.
- prop `count`: int (ro) — The number of chamfer edge sets in the collection.

### ChamferFeatureInput
This class defines the methods and properties that pertain to the definition of a chamfer feature.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `cornerType`: ChamferCornerTypes (rw) — Gets and sets the type of corner to be modeled when multiple edges connect at a vertex.
- prop `chamferEdgeSets`: ChamferEdgeSets (ro) — Returns the collection of edge sets for this chamfer feature input.

### ChamferFeatures
Collection that provides access to all of the existing chamfer features in a component and supports the ability to create new chamfer features.
- `item(index: int) -> ChamferFeature` — Function that returns the specified chamfer feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(input: ChamferFeatureInput) -> ChamferFeature` — Creates a new chamfer feature.
    - `input`: A ChamferFeatureInput object that defines the desired chamfer.
- `itemByName(name: str) -> ChamferFeature` — Function that returns the specified chamfer feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInput2() -> ChamferFeatureInput` — Creates a ChamferFeatureInput object.
- prop `count`: int (ro) — The number of chamfer features in the collection.

### CircularPatternConstraintInput
This class defines the methods and properties that pertain to the definition of a circular pattern in a sketch.
- prop `entities`: list[SketchEntity] (rw) — Gets and sets the entities to pattern.
- prop `centerPoint`: SketchPoint (rw) — Gets and sets the sketch point that defines the center of the pattern.
- prop `quantity`: ValueInput (rw) — Gets and sets quantity of the elements.
- prop `totalAngle`: ValueInput (rw) — Gets and sets total angle.
- prop `isSymmetric`: bool (rw) — Gets and sets if the angle extent is in one direction or is symmetric.
- prop `isSuppressed`: list[bool] (rw) — Specifies which, if any, instances of the pattern are suppressed.

### CircularPatternFeatureInput
This class defines the methods and properties that pertain to the definition of a circular pattern feature.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the input entities.
- prop `axis`: Base (rw) — Gets and sets the axis of circular pattern.
- prop `quantity`: ValueInput (rw) — Gets and sets quantity of the elements.
- prop `totalAngle`: ValueInput (rw) — Gets and sets total angle.
- prop `isSymmetric`: bool (rw) — Gets and sets if the angle extent is in one direction or symmetric.
- prop `patternComputeOption`: PatternComputeOptions (rw) — Gets and sets the compute option when patterning features.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### CircularPatternFeatures
Collection that provides access to all of the existing circular pattern features in a component and supports the ability to create new circular pattern features.
- `item(index: int) -> CircularPatternFeature` — Function that returns the specified circular pattern feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputEntities: ObjectCollection, axis: Base) -> CircularPatternFeatureInput` — Creates a CircularPatternFeatureInput object.
    - `inputEntities`: An ObjectCollection of the entities to pattern.
    - `axis`: Input linear entity or the entity has axis that defines axis of circular pattern.
- `add(input: CircularPatternFeatureInput) -> CircularPatternFeature` — Creates a new circular pattern feature.
    - `input`: A CircularPatternFeatureInput object that defines the desired circular pattern.
- `itemByName(name: str) -> CircularPatternFeature` — Function that returns the specified circular pattern feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of circular pattern features in the collection.

### CoilFeatureInput
This class defines the methods and properties that pertain to the definition of a coil feature.
- `setToRevolutionAndHeight(revolutions: ValueInput, height: ValueInput, angle: ValueInput) -> bool` — Sets the coil type to RevolutionsAndHeightCoilType.
    - `revolutions`: A ValueInput object that defines the number of revolutions.
    - `height`: A ValueInput object that defines the height.
    - `angle`: A ValueInput object that defines angle.
- `setToRevolutionsAndPitch(revolutions: ValueInput, pitch: ValueInput, angle: ValueInput) -> bool` — Sets the coil type to RevolutionsAndPitchCoilType.
    - `revolutions`: A ValueInput object that defines the number of revolutions.
    - `pitch`: A ValueInput object that defines the pitch.
    - `angle`: A ValueInput object that defines angle.
- `setToHeightAndPitchCoil(height: ValueInput, pitch: ValueInput, angle: ValueInput) -> bool` — Sets the coil type to HeightAndPitchCoilType.
    - `height`: A ValueInput object that defines the height.
    - `pitch`: A ValueInput object that defines the pitch.
    - `angle`: A ValueInput object that defines angle.
- `setToSpiral(revolutions: ValueInput, pitch: ValueInput) -> bool` — Sets the coil type to SpiralCoilType.
    - `revolutions`: A ValueInput object that defines the number of revolutions.
    - `pitch`: A ValueInput object that defines the pitch.
- prop `isSolid`: bool (rw) — Specifies if the coil should be created as a solid or surface.
- prop `revolutions`: ValueInput (ro) — Gets the revolutions number.
- prop `height`: ValueInput (ro) — Gets the height.
- prop `pitch`: ValueInput (ro) — Gets the pitch.
- prop `angle`: ValueInput (ro) — Gets the angle.
- prop `coilType`: CoilFeatureTypes (ro) — Gets the type of the coil.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the coil.
- prop `basePlane`: Base (rw) — Gets and sets the base plane.
- prop `isClockwiseRotation`: bool (rw) — Gets and sets whether the rotation is clockwise or counter-clockwise.
- prop `diameter`: ValueInput (rw) — Gets and sets the diameter.
- prop `coilSectionType`: CoilFeatureSectionTypes (rw) — Gets the section type of the coil.
- prop `coilSectionPosition`: CoilFeatureSectionPositions (rw) — Gets the section position of the coil.
- prop `sectionSize`: ValueInput (rw) — Gets and sets the section size.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### CoilFeatures
Collection that provides access to all of the existing coil features in a design and supports the ability to create new coil features.
- `item(index: int) -> CoilFeature` — Function that returns the specified coil feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> CoilFeature` — Function that returns the specified coil feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of coil features in the collection.

### CombineFeatureInput
This class defines the methods and properties that pertain to the definition of a combine feature.
- prop `targetBody`: BRepBody (rw) — Gets and sets the BRep Body object that represents the blank body.
- prop `toolBodies`: ObjectCollection (rw) — Gets and sets the BRep Body objects that represent the tool bodies.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the combine.
- prop `isNewComponent`: bool (rw) — Gets and sets a boolean value for whether or not a new component will be created with the results.
- prop `isKeepToolBodies`: bool (rw) — Gets and sets a boolean value for whether or not the tool bodies are retrained after the combine results.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### CombineFeatures
Collection that provides access to all of the existing Combine features in a component and supports the ability to create new Combine features.
- `item(index: int) -> CombineFeature` — Function that returns the specified combine feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(targetBody: BRepBody, toolBodies: ObjectCollection) -> CombineFeatureInput` — Creates a CombineFeatureInput object.
    - `targetBody`: A BRep body that represents the blank body.
    - `toolBodies`: An ObjectCollection containing one or more BRep bodies that represent tool bodies.
- `add(input: CombineFeatureInput) -> CombineFeature` — Creates a new combine feature.
    - `input`: A CombineFeatureInput object that defines the desired combine.
- `itemByName(name: str) -> CombineFeature` — Function that returns the specified combine feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of combine features in the collection.

### ConstructionAxis
ConstructionAxis Object
- `deleteMe() -> bool` — Deletes the construction axis.
- `createForAssemblyContext(occurrence: Occurrence) -> ConstructionAxis` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `geometry`: InfiniteLine3D (ro) — Returns an infinite line that represents the position and orientation of the construction axis.
- prop `name`: str (rw) — The name of the construction axis as it is shown in the browser.
- prop `definition`: ConstructionAxisDefinition (ro) — Returns the construction axis definition object which provides access to the information defining the construction axis.
- prop `isParametric`: bool (ro) — Indicates if this construction axis is parametric or not.
- prop `isDeletable`: bool (ro) — Indicates if this construction axis can be deleted.
- prop `isLightBulbOn`: bool (rw) — Indicates if the light bulb (as displayed in the browser) is on.
- prop `isVisible`: bool (ro) — Gets if the construction plane is visible.
- prop `parent`: Base (ro) — Returns the parent component or base feature.
- prop `component`: Component (ro) — Returns the component this construction plane belongs to.
- prop `timelineObject`: TimelineObject (ro) — Returns the timeline object associated with this construction axis.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `nativeObject`: ConstructionAxis (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `baseFeature`: BaseFeature (ro) — If this construction axis is associated with a base feature, this property will return that base feature.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this construction axis.
- prop `healthState`: FeatureHealthStates (ro) — Returns the current health state of this construction axis.
- prop `errorOrWarningMessage`: str (ro) — Returns the error or warning message in the case where the healthState property returns either WarningFeatureHealthState or ErrorFeatureHealthState.
- prop `entityToken`: str (ro) — Returns a token for the ConstructionAxis object.
- prop `isDerived`: bool (ro) — Returns if this construction axis is derived from another design.
- prop `deriveFeature`: DeriveFeature (ro) — Returns the DeriveFeature if this construction axis is derived from another design.
- prop `isUCSGeometry`: bool (ro) — ** This property is a preview feature and may change in future releases.
- prop `parentUCS`: UserCoordinateSystem (ro) — ** This property is a preview feature and may change in future releases.
- prop `isExtended`: bool (rw) — ** This property is a preview feature and may change in future releases.

### ConstructionAxisDefinition
A Base class to return the information (possibly parametric) used to define a ConstructionAxis.
- prop `parentConstructionAxis`: ConstructionAxis (ro) — Returns the ConstructionAxis object

### ConstructionAxisInput
A ConstructionAxisInput is a throwaway object used to create a ConstructionAxis The usage pattern is: a.
- `setByLine(line: InfiniteLine3D) -> bool` — This input method is for creating a non-parametric construction axis whose position in space is defined by an InfiniteLine3D object.
    - `line`: An InFiniteLine3D object
- `setByCircularFace(circularFace: BRepFace) -> bool` — This input method is for creating an axis coincident with the axis of a cylindrical, conical or torus face.
    - `circularFace`: The face from a cylinder, cone, or torus.
- `setByPerpendicularAtPoint(face: BRepFace, pointEntity: Base) -> bool` — This input method is for creating an axis that is normal to a face at a specified point.
    - `face`: A face (BRepFace object) to create the axis normal to.
    - `pointEntity`: A construction point, sketch point or vertex the axis is to pass through.
- `setByTwoPlanes(planarEntityOne: Base, planarEntityTwo: Base) -> bool` — This input method is for creating a construction axis coincident with the intersection of two planes or planar faces.
    - `planarEntityOne`: The first planar face or construction plane to intersect
    - `planarEntityTwo`: The second planar face or construction plane to intersect
- `setByTwoPoints(pointEntityOne: Base, pointEntityTwo: Base) -> bool` — This input method is for creating a construction axis that passes through the two points (work points, sketch points or vertices).
    - `pointEntityOne`: The first construction point, sketch point or vertex the axis passes through
    - `pointEntityTwo`: The second construction point, sketch point or vertex the axis passes through
- `setByEdge(edgeEntity: Base) -> bool` — This input method is for creating a construction axis from a specified linear/circular edge or sketch curve.
    - `edgeEntity`: A linear/circular edge, construction line, or sketch line
- `setByNormalToFaceAtPoint(face: BRepFace, pointEntity: Base) -> bool` — This input method if for creating a construction axis normal to a specified face or sketch profile and that passes through a specified point.
    - `face`: The face (BRepFace object) to create the axis normal to.
    - `pointEntity`: A construction point, sketch point or vertex the axis passes through.
- `setByNormalToFaceAtSnapPoint(face: BRepFace, snapPoint: ConstructionSnapPoint) -> bool` — This input method is for creating a construction axis normal to a specified face or sketch profile and that passes through the location described by a snap point.
    - `face`: The face (BRepFace object) to create the axis normal to.
    - `snapPoint`: The ConstructionSnapPoint describing the location the axis passes through.
- `setByTwoSnapPoints(snapPointOne: ConstructionSnapPoint, snapPointTwo: ConstructionSnapPoint) -> bool` — This input method is for creating a construction axis that passes through the two snap points.
    - `snapPointOne`: The first ConstructionSnapPoint the axis passes through.
    - `snapPointTwo`: The second ConstructionSnapPoint the axis passes through.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the ConstructionAxis is created based on geometry (e.g.
- prop `targetBaseOrFormFeature`: Base (rw) — When creating a construction axis that is owned by a base or form feature, set this property to the base or form feature you want to associate the new construction plane with.
- prop `isExtended`: bool (rw) — ** This property is a preview feature and may change in future releases.

### ConstructionPlane
ConstructionPlane Object
- `deleteMe() -> bool` — Deletes the construction plane.
- `createForAssemblyContext(occurrence: Occurrence) -> ConstructionPlane` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `geometry`: Plane (ro) — Returns a plane that represents the position and orientation of the construction plane.
- prop `name`: str (rw) — Returns the name of the construction plane as it is shown in the browser.
- prop `definition`: ConstructionPlaneDefinition (ro) — Returns the ConstructionPlaneDefinition object which provides access to the information defining this ConstructionPlane.
- prop `isDeletable`: bool (ro) — Indicates if this construction plane can be deleted.
- prop `isParametric`: bool (ro) — Indicates if this construction plane is parametric or not.
- prop `isLightBulbOn`: bool (rw) — Indicates if the light bulb (as displayed in the browser) is on.
- prop `isVisible`: bool (ro) — Indicates if the construction plane is visible.
- prop `displayBounds`: BoundingBox2D (rw) — Gets and sets the display size of the construction plane.
- prop `parent`: Base (ro) — Returns the parent component or base feature.
- prop `component`: Component (ro) — Returns the component this construction plane belongs to.
- prop `timelineObject`: TimelineObject (ro) — Returns the timeline object associated with this construction plane.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `nativeObject`: ConstructionPlane (ro) — The NativeObject is the object outside the context of an assembly.
- prop `baseFeature`: BaseFeature (ro) — If this construction plane is associated with a base feature, this property will return that base feature.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this construction plane.
- prop `healthState`: FeatureHealthStates (ro) — Returns the current health state of this construction plane.
- prop `errorOrWarningMessage`: str (ro) — Returns the error or warning message in the case where the healthState property returns either WarningFeatureHealthState or ErrorFeatureHealthState.
- prop `transform`: Matrix3D (rw) — Returns the current position and orientation of the construction plane as a matrix.
- prop `entityToken`: str (ro) — Returns a token for the ConstructionPlane object.
- prop `isDerived`: bool (ro) — Returns if this construction plane is derived from another design.
- prop `deriveFeature`: DeriveFeature (ro) — Returns the DeriveFeature if this construction plane is derived from another design.
- prop `isUCSGeometry`: bool (ro) — ** This property is a preview feature and may change in future releases.
- prop `parentUCS`: UserCoordinateSystem (ro) — ** This property is a preview feature and may change in future releases.
- prop `isExtended`: bool (rw) — Gets and sets whether the construction plane uses the extended display mode.

### ConstructionPlaneDefinition
A Base class to return the information, possibly parametric, used to define the ConstructionPlane.
- prop `parentConstructionPlane`: ConstructionPlane (ro) — Returns the ConstructionPlane object

### ConstructionPlaneInput
A ConstructionPlaneInput is a throwaway object used to create a ConstructionPlane.
- `setByPlane(plane: Plane) -> bool` — This input method is for creating a non-parametric construction plane positioned in space as defined by the input Plane object.
    - `plane`: A transient plane object
- `setByOffset(planarEntity: Base, offset: ValueInput) -> bool` — This input method is for creating a construction plane that is offset from a planar face or construction plane at a specified distance.
    - `planarEntity`: A plane, planar face or construction plane from which to create the offset plane.
    - `offset`: ValueInput object that specifies the offset distance for the plane.
- `setByAngle(linearEntity: Base, angle: ValueInput, planarEntity: Base) -> bool` — This input method is for creating a construction plane through an edge, axis or line at a specified angle.
    - `linearEntity`: The axis about which to rotate the plane.
    - `angle`: The angle at which to create the plane.
    - `planarEntity`: The planar face or construction plane the angle is measured from.
- `setByTangent(tangentFace: BRepFace, angle: ValueInput, planarEntity: Base) -> bool` — This input method is for creating a construction plane tangent to a cylindrical or conical face at a specified point.
    - `tangentFace`: A cylindrical or conical face to create the plane tangent to.
    - `angle`: The angle relative to the planarEntity input at which to create the tangent plane.
    - `planarEntity`: The planar face or construction plane the tangent is measured from.
- `setByTwoPlanes(planarEntityOne: Base, planarEntityTwo: Base) -> bool` — This input method is for creating a construction plane at the midpoint between two planar faces or construction planes.
    - `planarEntityOne`: The first planar face or construction plane to create a bisecting plane between
    - `planarEntityTwo`: The second planar face or construction plane to create a bisecting plane between
- `setByTwoEdges(linearEntityOne: Base, linearEntityTwo: Base) -> bool` — This input method is for creating a construction plane that passes through two coplanar linear entities or axes.
    - `linearEntityOne`: The first of two coplanar linear entities to define the plane
    - `linearEntityTwo`: The second of two coplanar linear entities to define the plane
- `setByThreePoints(pointEntityOne: Base, pointEntityTwo: Base, pointEntityThree: Base) -> bool` — This input method is for creating a construction plane through three points that define a triangle.
    - `pointEntityOne`: The first construction point, sketch point or vertex in the triangle
    - `pointEntityTwo`: The second construction point, sketch point or vertex in the triangle
    - `pointEntityThree`: The third construction point, sketch point or vertex in the triangle
- `setByTangentAtPoint(tangentFace: BRepFace, pointEntity: Base) -> bool` — This input method is for creating a construction plane tangent to a face and aligned to a point.
    - `tangentFace`: A face to create the plane tangent to
    - `pointEntity`: A construction point, sketch point or vertex the tangent plane aligns to.
- `setByOffsetThroughPoint(planarEntity: Base, point: Base) -> bool` — Defines a construction plane that is offset from a planar face or construction plane and whose offset distance is defined by a vertex, sketch point, or construction point where the plane passes through the point.
    - `planarEntity`: A planar BRepFace, ConstructionPlane, or Plane object that the new construction plane will be offset from.
    - `point`: A BRepVertex, SketchPoint, ConstructionPoint, or Point3D that defines the offset distance.
- `setByAngleOnCurvedFace(curvedFace: Base, angle: ValueInput, planarEntity: Base) -> bool` — This input method is for creating a construction plane through the axis inferred from a cylindrical or conical curved face at a specified angle.
    - `curvedFace`: The cylindrical or conical curved face from which the axis of rotation is inferred.
    - `angle`: The angle at which to create the plane.
    - `planarEntity`: The planar face or construction plane the angle is measured from.
- `setByPerpendicularToPlane(planarEntity: Base, distance: ValueInput = None, referenceEntity: Base = None, useUDirection: bool = True) -> bool` — This input method creates a construction plane that is perpendicular to the input face or plane.
    - `planarEntity`: The face or plane the new construction plane will be perpendicular to.
    - `distance`: An optional ValueInput specifying the offset distance of the perpendicular plane from its base position.
    - `referenceEntity`: An optional reference entity that the new plane passes through.
    - `useUDirection`: True to align the perpendicular plane with the U axis of the reference face; false to align with the V axis.
- `setByThreeSnapPoints(snapPointOne: ConstructionSnapPoint, snapPointTwo: ConstructionSnapPoint, snapPointThree: ConstructionSnapPoint) -> bool` — This input method is for creating a construction plane through three snap points.
    - `snapPointOne`: The first ConstructionSnapPoint the plane passes through.
    - `snapPointTwo`: The second ConstructionSnapPoint the plane passes through.
    - `snapPointThree`: The third ConstructionSnapPoint the plane passes through.
- `setByPath(path: Path, distanceType: PathDistanceTypes, distance: ValueInput) -> bool` — This input method is for creating a construction plane normal to the specified path at a specified position along the path.
    - `path`: Specifies the Path object the construction plane will be created on.
    - `distanceType`: Specifies PathDistanceTypes value indicating the measurement type for distance.
    - `distance`: Specifies the distance to determine the position on the specified path to place the construction plane.
- `setByPathToObject(path: Path, toObject: Base, offset: ValueInput) -> bool` — This input method is for creating a construction plane normal to the specified path at the position where the path meets the target point entity, with an optional signed offset along the path from that …
    - `path`: Specifies the Path object the construction plane will be created on.
    - `toObject`: Specifies the point entity the construction plane is positioned to.
    - `offset`: Specifies the signed offset from the target along the path.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the ConstructionPlane is created based on geometry (e.g.
- prop `targetBaseOrFormFeature`: Base (rw) — When creating a construction plane that is owned by a base or form feature, set this property to the base or form feature you want to associate the new construction plane with.
- prop `isExtended`: bool (rw) — Gets and sets whether the construction plane will use the extended display mode when created.

### ConstructionPlanes
Provides access to the construction planes within a component and provides methods to create new construction planes.
- `item(index: int) -> ConstructionPlane` — Function that returns the specified construction plane using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> ConstructionPlane` — Returns the specified construction plane using the name of the construction plane as it is displayed in the browser.
    - `name`: The name of the construction plane as it is displayed in the browser.
- `createInput(occurrenceForCreation: Occurrence = None) -> ConstructionPlaneInput` — Create a ConstructionPlaneInput object that is in turn used to create a ConstructionPlane.
    - `occurrenceForCreation`: A creation occurrence is needed if the input is in another component AND the construction plane is not in the root component.
- `add(input: ConstructionPlaneInput) -> ConstructionPlane` — Creates and adds a new ConstructionPlane using the creation parameters in the ConstructionPlaneInput.
    - `input`: A ConstructionPlaneInput object
- prop `count`: int (ro) — Returns the number of construction planes in the collection.
- prop `component`: Component (ro) — Returns the component that owns this collection.

### ConstructionPoint
ConstructionPoint Object
- `deleteMe() -> bool` — Deletes the construction point.
- `createForAssemblyContext(occurrence: Occurrence) -> ConstructionPoint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `geometry`: Point3D (ro) — Returns a Point3D object that represents the position of the construction point.
- prop `name`: str (rw) — The name of the construction point as it is displayed in the browser.
- prop `definition`: ConstructionPointDefinition (ro) — Returns the construction point definition object which provides access to the information defining the construction point.
- prop `isDeletable`: bool (ro) — Indicates if this construction point can be deleted.
- prop `isLightBulbOn`: bool (rw) — Indicates if the light bulb (as displayed in the browser) is on.
- prop `isVisible`: bool (ro) — Gets if the construction point is visible.
- prop `parent`: Base (ro) — Returns the parent component or base feature.
- prop `component`: Component (ro) — Returns the component this construction point belongs to.
- prop `isParametric`: bool (ro) — Indicates if the construction point is parametric.
- prop `timelineObject`: TimelineObject (ro) — Returns the timeline object associated with this construction point.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `nativeObject`: ConstructionPoint (ro) — The NativeObject is the object outside the context of an assembly.
- prop `baseFeature`: BaseFeature (ro) — If this construction point is associated with a base feature, this property will return that base feature.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this construction point.
- prop `healthState`: FeatureHealthStates (ro) — Returns the current health state of this construction point.
- prop `errorOrWarningMessage`: str (ro) — Returns the error or warning message in the case where the healthState property returns either WarningFeatureHealthState or ErrorFeatureHealthState.
- prop `entityToken`: str (ro) — Returns a token for the ConstructionPoint object.
- prop `isDerived`: bool (ro) — Returns if this construction point is derived from another design.
- prop `deriveFeature`: DeriveFeature (ro) — Returns the DeriveFeature if this construction point is derived from another design.
- prop `isUCSGeometry`: bool (ro) — ** This property is a preview feature and may change in future releases.
- prop `parentUCS`: UserCoordinateSystem (ro) — ** This property is a preview feature and may change in future releases.

### ConstructionPointDefinition
A Base class to return the information (possibly parametric) used to define a ConstructionPoint.
- prop `parentConstructionPoint`: ConstructionPoint (ro) — Returns the ConstructionPoint object

### ConstructionPointInput
A ConstructionPointInput is a throwaway object used to create a ConstructionPoint.
- `setByTwoEdges(edgeOne: Base, edgeTwo: Base) -> bool` — This input method is for creating a construction point at the intersection of the two linear edges or sketch lines.
    - `edgeOne`: The first B-Rep edge or sketch line.
    - `edgeTwo`: The second B-Rep edge or sketch line.
- `setByThreePlanes(planeOne: Base, planeTwo: Base, planeThree: Base) -> bool` — This input method is for creating a construction point at the intersection of the three planes or planar faces.
    - `planeOne`: The first plane or planar face to intersect
    - `planeTwo`: The second plane or planar face to intersect
    - `planeThree`: The third plane or planar face to intersect
- `setByEdgePlane(edge: Base, plane: Base) -> bool` — This input method is for creating a construction point at the intersection of a construction plane, planar face or sketch profile and a linear edge, construction axis or sketch line.
    - `edge`: A linear B-Rep edge, construction axis or sketch line.
    - `plane`: A plane, planar B-Rep face or construction plane.
- `setByCenter(circularEntity: Base) -> bool` — This input method is for creating a construction point at the center of a spherical face (sphere or torus), circular edge or sketch arc/circle This can result in a parametric or non-parametric construction point depending …
    - `circularEntity`: A spherical face (sphere or torus), circular edge or sketch arc/circle
- `setByPoint(point: Base) -> bool` — This input method is for creating a construction point on the specified point or vertex.
    - `point`: A B-Rep vertex, SketchPoint, or Point object
- `setByPath(path: Path, distanceType: PathDistanceTypes, distance: ValueInput) -> bool` — This input method is for creating a construction point on the specified path.
    - `path`: Specifies the Path object the construction point will be created on.
    - `distanceType`: Specifies PathDistanceTypes value indicating the measurement type for distance.
    - `distance`: Specifies the distance to determine the position on the specified path to place the new construction point.
- `setBySnapPoint(snapPoint: ConstructionSnapPoint) -> bool` — This input method is for creating a construction point at the supplied snap point.
    - `snapPoint`: The ConstructionSnapPoint defining the location of the construction point.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an occurrence for creation needs to be specified when the ConstructionPoint is created based on geometry (e.g.
- prop `targetBaseOrFormFeature`: Base (rw) — When creating a construction point that is owned by a base or form feature, set this property to the base or form feature you want to associate the new construction point with.

### ConstructionPoints
Provides access to the construction points within a component and provides methods to create new construction points.
- `item(index: int) -> ConstructionPoint` — Function that returns the specified construction point using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> ConstructionPoint` — Returns the specified construction point using the name of the construction point as it is displayed in the browser.
    - `name`: The name of the construction point as it is displayed in the browser.
- `createInput(occurrenceForCreation: Occurrence = None) -> ConstructionPointInput` — Create a ConstructionPointInput object that is in turn used to create a ConstructionPoint.
    - `occurrenceForCreation`: A creation occurrence is needed if the input is in another component AND the construction point is not in the root component.
- `add(input: ConstructionPointInput) -> ConstructionPoint` — Creates a new construction point.
    - `input`: A ConstructionPointInput object
- prop `count`: int (ro) — The number of construction points in the collection.
- prop `component`: Component (ro) — The component that owns this collection.

### DeleteFaceFeatures
Collection that provides access to all of the existing DeleteFaceFeature features in a component and supports the ability to create new DeleteFaceFeature features.
- `item(index: int) -> DeleteFaceFeature` — Function that returns the specified DeleteFaceFeature object using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> DeleteFaceFeature` — Function that returns the specified DeleteFaceFeature object using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `add(facesToDelete: Base) -> DeleteFaceFeature` — Creates a new SurfaceDeleteFace feature.
    - `facesToDelete`: A single BRepFace or an ObjectCollection containing multiple BRepFace objects.
- prop `count`: int (ro) — The number of DeleteFaceFeature objects in the collection.

### DraftAnalyses
Provides access to any draft analyses results in the design.
- `item(index: int) -> DraftAnalysis` — A method that returns the specified DraftAnalysis object using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> DraftAnalysis` — A method that returns the specified DraftAnalysis object using the name of the analysis as displayed in the browser.
    - `name`: The name of the DraftAnalysis object as displayed in the browser.
- prop `count`: int (ro) — Returns the number of DraftAnalysis objects in the collection.

### DraftFeatureInput
This class defines the methods and properties that pertain to the definition of a draft feature.
- `setSingleAngle(isSymmetric: bool, angle: ValueInput) -> bool` — Defines the draft to be defined so that a single angle is used for all drafts.
    - `isSymmetric`: Set to true if the faces are to be split along the plane or parting line and drafted symmetrically.
    - `angle`: The ValueInput object that defines the angle of the draft.
- `setTwoAngles(angleOne: ValueInput, angleTwo: ValueInput) -> bool` — Defines both angles to use when the surfaces are split along the draft plane or parting line and the faces on each side of the plane are drafted independently.
    - `angleOne`: The ValueInput object that defines the angle for the faces on the first side of the draft plane or parting line.
    - `angleTwo`: The ValueInput object that defines the angle for the faces on the second side of the draft plane or parting line.
- `setFixedPartingLineDraftFeatureType(partingLineCurves: list[Base], isChained: bool) -> bool` — ** This method is a preview feature and may change in future releases.
    - `partingLineCurves`: An array that contains a combination of sketch curves and BRepEdge objects to define the parting line.
    - `isChained`: If true, curves that are connected to any of the input parting line curves will also be included in the parting line.
- `setMovingPartingLineDraftFeatureType(partingLineCurves: list[Base], isChained: bool, direction: MovingPartingLineDirections, angle: ValueInput, fixedEdges: list[BRepEdge]) -> bool` — ** This method is a preview feature and may change in future releases.
    - `partingLineCurves`: An array that contains a combination of sketch curves and BRepEdge objects to define the parting line.
    - `isChained`: If true, curves that are connected to any of the input parting line curves will also be included in the parting line.
    - `direction`: Specifies how the angle is calculated to determine how the parting line is moved.
    - `angle`: The angle of the draft.
    - `fixedEdges`: An array containing the edges that should not deform when the parting line moves.
- `setFixedPlaneDraftFeatureType() -> bool` — ** This method is a preview feature and may change in future releases.
- prop `inputFaces`: list[BRepFace] (rw) — Gets and sets the input faces.
- prop `plane`: Base (rw) — Gets and sets the plane that defines the direction in which the draft is applied.
- prop `isTangentChain`: bool (rw) — Gets and sets if any faces that are tangentially connected to any of the input faces will also be included in setting InputEntities.
- prop `isDirectionFlipped`: bool (rw) — Gets and sets if the direction of the draft is flipped.
- prop `angleOne`: ValueInput (ro) — Gets the first, or the only angle in the case of a single angle definition.
- prop `angleTwo`: ValueInput (ro) — Gets the second angle.
- prop `isSymmetric`: bool (ro) — Gets if the draft is symmetric from the draft plane.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `draftType`: DraftFeatureTypes (ro) — ** This property is a preview feature and may change in future releases.
- prop `partingLineType`: PartingLineTypes (ro) — ** This property is a preview feature and may change in future releases.
- prop `movingPartingLineDirection`: MovingPartingLineDirections (ro) — ** This property is a preview feature and may change in future releases.
- prop `partingLineCurves`: list[Base] (ro) — ** This property is a preview feature and may change in future releases.
- prop `movingPartingLineFixedEdges`: list[BRepEdge] (ro) — ** This property is a preview feature and may change in future releases.

### DraftFeatures
Collection that provides access to all of the existing draft features in a component and supports the ability to create new draft features.
- `item(index: int) -> DraftFeature` — Function that returns the specified draft feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputFaces: list[BRepFace], plane: Base, isTangentChain: bool = True) -> DraftFeatureInput` — Creates a DraftFeatureInput object.
    - `inputFaces`: BRepFace array that contains the faces to which draft will be applied.
    - `plane`: Input object that defines the direction in which the draft is applied.
    - `isTangentChain`: A boolean value for setting whether or not faces that are tangentially connected to any of the input faces (if any) will also be included.
- `add(input: DraftFeatureInput) -> DraftFeature` — Creates a new draft feature.
    - `input`: A DraftFeatureInput object that defines the desired draft.
- `itemByName(name: str) -> DraftFeature` — Function that returns the specified draft feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of draft features in the collection.

### EmbossFeatureInput
This class defines the methods and properties that pertain to the definition of an emboss feature.
- prop `profiles`: list[Base] (rw) — Gets and sets an array of Profile objects that define the shape of the emboss.
- prop `inputFaces`: list[BRepFace] (rw) — Gets and sets an array of BRepFace objects that define the faces the emboss will be performed on.
- prop `isTangentChain`: bool (rw) — Gets and sets whether any faces that are tangentially connected to any of the input faces will also be used.
- prop `depth`: ValueInput (rw) — Gets and sets the ValueInput object that defines the depth of the emboss.
- prop `horizontalDistance`: ValueInput (rw) — Gets and sets the horizontal offset distance.
- prop `verticalDistance`: ValueInput (rw) — Gets and sets the vertical offset distance.
- prop `rotationAngle`: ValueInput (rw) — Gets and sets the rotation angle.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the emboss feature is created based on geometry (e.g.

### EmbossFeatures
Collection that provides access to all of the existing emboss features in a component and supports the ability to create new emboss features.
- `item(index: int) -> EmbossFeature` — Function that returns the specified emboss feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> EmbossFeature` — Function that returns the specified emboss feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInput(profiles: list[Base], faces: list[BRepFace], depth: ValueInput) -> EmbossFeatureInput` — Creates an EmbossFeatureInput object.
    - `profiles`: An array of Profile objects that define the shape of the emboss.
    - `faces`: An array of BRepFace objects that define the faces the emboss will be performed on.
    - `depth`: A ValueInput object that defines the depth of the emboss.
- `add(input: EmbossFeatureInput) -> EmbossFeature` — Creates a new emboss feature.
    - `input`: An EmbossFeatureInput object that defines the desired emboss feature.
- prop `count`: int (ro) — The number of emboss features in the collection.

### ExtendFeatureInput
This class defines the methods and properties that pertain to the definition of an extend feature.
- prop `edges`: ObjectCollection (rw) — Gets and sets the edges to extend
- prop `distance`: ValueInput (rw) — Gets and sets the ValueInput object that defines the extend distance
- prop `extendType`: SurfaceExtendTypes (rw) — Gets and sets surface extend type to use
- prop `isChainingEnabled`: bool (rw) — Gets and sets if all edges that are tangent or curvature continuous, and end point connected, will be found automatically and extended.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `extendAlignment`: SurfaceExtendAlignment (rw) — Gets and sets surface extend alignment to use.

### ExtendFeatures
Collection that provides access to all of the existing Extend features in a component and supports the ability to create new Extend features.
- `item(index: int) -> ExtendFeature` — Function that returns the specified extend feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(edges: ObjectCollection, distance: ValueInput, extendType: SurfaceExtendTypes, isChainingEnabled: bool = True) -> ExtendFeatureInput` — Creates an ExtendFeatureInput object.
    - `edges`: The surface edges to extend.
    - `distance`: ValueInput object that defines the distance to extend the face/s.
    - `extendType`: The extension type to use when extending the face(s).
    - `isChainingEnabled`: An optional boolean argument whose default is true.
- `add(input: ExtendFeatureInput) -> ExtendFeature` — Creates a new extend feature.
    - `input`: An ExtendFeatureInput object that defines the desired extend feature.
- `itemByName(name: str) -> ExtendFeature` — Function that returns the specified extend feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of Extend features in the collection.

### ExtentDefinition
The base class for the various definition objects used to define the extent of a feature.
- prop `parentFeature`: Feature (ro) — Returns the parent feature that this definition is associated with.

### ExtrudeFeatureInput
This class defines the methods and properties that pertain to the definition of an extrude feature.
- `setOneSideExtent(extent: ExtentDefinition, direction: ExtentDirections, taperAngle: ValueInput = None) -> bool` — Defines the extrusion to go in one direction from the profile.
    - `extent`: An ExtentDefinition object that defines how the extent of the extrusion is defined.
    - `direction`: Specifies the direction of the extrusion.
    - `taperAngle`: Optional argument that specifies the taper angle.
- `setTwoSidesExtent(sideOneExtent: ExtentDefinition, sideTwoExtent: ExtentDefinition, sideOneTaperAngle: ValueInput = None, sideTwoTaperAngle: ValueInput = None) -> bool` — Defines the extrusion to go in both directions from the profile.
    - `sideOneExtent`: An ExtentDefinition object that defines how the extent of the extrusion towards side one is defined.
    - `sideTwoExtent`: An ExtentDefinition object that defines how the extent of the extrusion towards side two is defined.
    - `sideOneTaperAngle`: Optional argument that specifies the taper angle for side one.
    - `sideTwoTaperAngle`: Optional argument that specifies the taper angle for side two.
- `setSymmetricExtent(distance: ValueInput, isFullLength: bool, taperAngle: ValueInput = None) -> bool` — Defines the extrusion to go symmetrically in both directions from the profile.
    - `distance`: The distance of the extrusions.
    - `isFullLength`: Defines if the value defines the full length of the extrusion or half of the length.
    - `taperAngle`: Optional argument that specifies the taper angle.
- `setThinExtrude(thinExtrudeWallLocationOne: ThinExtrudeWallLocation, thinExtrudeWallThicknessOne: ValueInput, thinExtrudeWallLocationTwo: ThinExtrudeWallLocation = ThinExtrudeWallLocation.Side1, thinExtrudeWallThicknessTwo: ValueInput = None) -> bool` — Changes the extrude feature to be a thin extrude.
    - `thinExtrudeWallLocationOne`: Specifies the position of the thin wall extrude with respect to the profile being extruded.
    - `thinExtrudeWallThicknessOne`: A ValueInput object that defines the thickness for a single sided thin extrude or side one of a two-sided extrusion .
    - `thinExtrudeWallLocationTwo`: Optional argument that specifies the position of side two of a two-sided extrusion.
    - `thinExtrudeWallThicknessTwo`: Optional argument that is a ValueInput object that defines the thickness for side two of a two-sided extrusion.
- prop `profile`: Base (rw) — Gets and sets the profiles or planar faces used to define the shape of the extrude.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the extrusion.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the Extrusion is created based on geometry (e.g.
- prop `isSolid`: bool (rw) — Specifies if the extrusion should be created as a solid or surface.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `startExtent`: ExtentDefinition (rw) — Gets and sets the extent used to define the start of the extrusion.
- prop `extentOne`: ExtentDefinition (ro) — Gets the extent assigned for a single sided extrude or side one of a two-sided extrusion.
- prop `extentTwo`: ExtentDefinition (ro) — Gets the extent assigned for side two of the extrusion.
- prop `taperAngleOne`: ValueInput (ro) — Gets the value that will be used as the taper angle for a single sided extrusion or side one of a two-sided extrusion.
- prop `taperAngleTwo`: ValueInput (ro) — Gets the value that will be used as the taper angle for side two of a two-sided extrusion.
- prop `hasTwoExtents`: bool (ro) — Property that indicates if the extrusion is a single or two-sided extrusion.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `isThinExtrude`: bool (rw) — Sets or returns whether the extrude is a thin extrude.
- prop `thinExtrudeWallLocationOne`: ThinExtrudeWallLocation (rw) — Gets and sets the wall location for a one sided thin extrude or side one of a two sided thin extrude
- prop `thinExtrudeWallLocationTwo`: ThinExtrudeWallLocation (rw) — Gets and sets the wall location for side two of a two sided thin extrude
- prop `thinExtrudeWallThicknessOne`: ValueInput (rw) — Gets and sets the wall thickness for a one sided thin extrude or side one of a two sided thin extrude
- prop `thinExtrudeWallThicknessTwo`: ValueInput (rw) — Gets and sets the wall thickness for side two of a two sided thin extrude

### ExtrudeFeatures
Collection that provides access to all of the existing extrude features in a design and supports the ability to create new extrude features.
- `item(index: int) -> ExtrudeFeature` — Function that returns the specified extrude feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(profile: Base, operation: FeatureOperations) -> ExtrudeFeatureInput` — Creates a new ExtrudeFeatureInput object that is used to specify the input needed to create a new extrude feature.
    - `profile`: The profile argument can be a single Profile, a single planar face, a single SketchText object, or an ObjectCollection consisting of multiple profiles, planar faces, and sketch texts.
    - `operation`: The feature operation to perform.
- `add(input: ExtrudeFeatureInput) -> ExtrudeFeature` — Creates a new extrude feature based on the information defined by the provided ExtrudeFeatureInput object.
    - `input`: The ExtrudeFeatureInput object that specifies the input needed to create a new extrude feature.
- `itemByName(name: str) -> ExtrudeFeature` — Function that returns the specified extrude feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `addSimple(profile: Base, distance: ValueInput, operation: FeatureOperations) -> ExtrudeFeature` — Creates a basic extrusion that goes from the profile plane the specified distance.
    - `profile`: The profile argument can be a single Profile, a single planar face, a single SketchText object, or an ObjectCollection consisting of multiple profiles, planar faces, and sketch texts.
    - `distance`: ValueInput object that defines the extrude distance.
    - `operation`: The feature operation to perform.
- prop `count`: int (ro) — The number of extrude features in the collection.

### Feature
Base class object representing all features.
- `deleteMe() -> bool` — Deletes the feature.
- `dissolve() -> bool` — Dissolves the feature so that the feature information is lost and only the B-Rep geometry defined by the feature remains.
- prop `name`: str (rw) — Returns the name of the feature as seen in the browser (non-parametric) or in the timeline (parametric).
- prop `isSuppressed`: bool (rw) — Gets and sets if this feature is suppressed.
- prop `isParametric`: bool (ro) — Indicates if this feature is parametric or not.
- prop `faces`: BRepFaces (ro) — Returns the faces that were created by this feature.
- prop `parentComponent`: Component (ro) — Returns the parent component that owns this feature.
- prop `linkedFeatures`: FeatureList (ro) — Returns the set of features that are linked to this feature.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `timelineObject`: TimelineObject (ro) — Returns the timeline object associated with this feature.
- prop `bodies`: BRepBodies (ro) — Returns the bodies that were modified or created by this feature.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this face.
- prop `baseFeature`: BaseFeature (ro) — If this feature is associated with a base feature, this property will return that base feature.
- prop `healthState`: FeatureHealthStates (ro) — Returns the current health state of the feature.
- prop `errorOrWarningMessage`: str (ro) — Returns the error or warning message in the case where the healthState property returns either WarningFeatureHealthState or ErrorFeatureHealthState.
- prop `entityToken`: str (ro) — Returns a token for the Feature object.

### Features
The features collection which provides access to all existing features.
- `item(index: int) -> Feature` — Function that returns the specified feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createPath(curve: Base, isChain: bool = True) -> Path` — Method that creates a Path used to define the shape of a Sweep feature.
    - `curve`: A SketchCurve or an ObjectCollection containing multiple sketch entities and/or BRepEdge objects.
    - `isChain`: Optional argument, that defaults to true.
- `itemByName(name: str) -> Feature` — Function that returns the specified feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — Returns the number of features in the collection.
- prop `extrudeFeatures`: ExtrudeFeatures (ro) — Returns the collection that provides access to the extrude features within the component and supports the creation of new extrude features.
- prop `revolveFeatures`: RevolveFeatures (ro) — Returns the collection that provides access to the revolve features within the component and supports the creation of new revolved features.
- prop `holeFeatures`: HoleFeatures (ro) — Returns the collection that provides access to the hole features within the component and supports the creation of new hole features.
- prop `filletFeatures`: FilletFeatures (ro) — Returns the collection that provides access to the fillet features within the component and supports the creation of new fillet features.
- prop `sweepFeatures`: SweepFeatures (ro) — Returns the collection that provides access to the sweep features within the component and supports the creation of new sweep features.
- prop `chamferFeatures`: ChamferFeatures (ro) — Returns the collection that provides access to the chamfer features within the component and supports the creation of new chamfer features.
- prop `shellFeatures`: ShellFeatures (ro) — Returns the collection that provides access to the shell features within the component and supports the creation of new shell features.
- prop `mirrorFeatures`: MirrorFeatures (ro) — Returns the collection that provides access to the mirror features within the component and supports the creation of new mirror features.
- prop `circularPatternFeatures`: CircularPatternFeatures (ro) — Returns the collection that provides access to the circular pattern features within the component and supports the creation of new circular pattern features.
- prop `rectangularPatternFeatures`: RectangularPatternFeatures (ro) — Returns the collection that provides access to the rectangular pattern features within the component and supports the creation of new rectangular pattern features.
- prop `pathPatternFeatures`: PathPatternFeatures (ro) — Returns the collection that provides access to the path pattern features within the component and supports the creation of new path pattern features.
- prop `combineFeatures`: CombineFeatures (ro) — Returns the collection that provides access to the combine features within the component and supports the creation of new combine features.
- prop `threadFeatures`: ThreadFeatures (ro) — Returns the collection that provides access to the thread features within the component and supports the creation of new thread features.
- prop `draftFeatures`: DraftFeatures (ro) — Returns the collection that provides access to the draft features within the component and supports the creation of new draft features.
- prop `scaleFeatures`: ScaleFeatures (ro) — Returns the collection that provides access to the scale features within the component and supports the creation of new scale features.
- prop `replaceFaceFeatures`: ReplaceFaceFeatures (ro) — Returns the collection that provides access to the replaceFace features within the component and supports the creation of new replaceFace features.
- prop `moveFeatures`: MoveFeatures (ro) — Returns the collection that provides access to the Move features within the component and supports the creation of new Move features.
- prop `splitFaceFeatures`: SplitFaceFeatures (ro) — Returns the collection that provides access to the SplitFace features within the component and supports the creation of new SplitFace features
- prop `splitBodyFeatures`: SplitBodyFeatures (ro) — Returns the collection that provides access to the SplitBody features within the component and supports the creation of new SplitBody features
- prop `silhouetteSplitFeatures`: SilhouetteSplitFeatures (ro) — Returns the collection that provides access to the Parting Line Split features within the component and supports the creation of new Parting Line Split features
- prop `offsetFeatures`: OffsetFeatures (ro) — Returns the collection that provides access to the Offset features within the component and supports the creation of new Offset features.
- prop `extendFeatures`: ExtendFeatures (ro) — Returns the collection that provides access to the Extend features within the component and supports the creation of new Extend features.
- prop `stitchFeatures`: StitchFeatures (ro) — Returns the collection that provides access to the Stitch features within the component and supports the creation of new Stitch features.
- prop `boundaryFillFeatures`: BoundaryFillFeatures (ro) — Returns the collection that provides access to the Boundary Fill features within the component and supports the creation of new Boundary Fill features.
- prop `trimFeatures`: TrimFeatures (ro) — Returns the collection that provides access to the Trim features within the component and supports the creation of new Trim features.
- prop `thickenFeatures`: ThickenFeatures (ro) — Returns the collection that provides access to the Thicken features within the component and supports the creation of new Thicken features.
- prop `unstitchFeatures`: UnstitchFeatures (ro) — Returns the collection that provides access to the Unstitch features within the component and supports the creation of new Unstitch features.
- prop `removeFeatures`: RemoveFeatures (ro) — Returns the collection that provides access to the Remove features within the component and supports the creation of new Remove features.
- prop `baseFeatures`: BaseFeatures (ro) — Returns the collection that provides access to the existing base features and supports the creation of new base features.
- prop `coilFeatures`: CoilFeatures (ro) — Returns the collection that provides access to the Coil Primitive features within the component.
- prop `boxFeatures`: BoxFeatures (ro) — Returns the collection that provides access to the existing box features.
- prop `cylinderFeatures`: CylinderFeatures (ro) — Returns the collection that provides access to the existing cylinder features.
- prop `sphereFeatures`: SphereFeatures (ro) — Returns the collection that provides access to the existing sphere features.
- prop `torusFeatures`: TorusFeatures (ro) — Returns the collection that provides access to the existing torus features.
- prop `pipeFeatures`: PipeFeatures (ro) — Returns the collection that provides access to the existing pipe features.
- prop `ribFeatures`: RibFeatures (ro) — Returns the collection that provides access to the existing rib features.
- prop `webFeatures`: WebFeatures (ro) — Returns the collection that provides access to the existing web features.
- prop `formFeatures`: FormFeatures (ro) — Returns the collection that provides access to the existing form features.
- prop `reverseNormalFeatures`: ReverseNormalFeatures (ro) — Returns the collection that provides access to the Reverse Normal features within the component and supports the creation of new Reverse Normal features.
- prop `patchFeatures`: PatchFeatures (ro) — Returns the collection that provides access to the Patch features within the component and supports the creation of new Patch features.
- prop `loftFeatures`: LoftFeatures (ro) — Returns the collection that provides access to the existing loft features and supports the creation of new loft features.
- prop `surfaceDeleteFaceFeatures`: SurfaceDeleteFaceFeatures (ro) — Returns the collection that provides access to the existing Surface Delete Face features.
- prop `deleteFaceFeatures`: DeleteFaceFeatures (ro) — Returns the collection that provides access to the existing Delete Face features.
- prop `offsetFacesFeatures`: OffsetFacesFeatures (ro) — Returns the collection that provides access to the existing Offset Face features.
- prop `copyPasteBodies`: CopyPasteBodies (ro) — Returns the collection that provides access to the existing copy-paste features and supports the creation of new copy-paste features.
- prop `cutPasteBodies`: CutPasteBodies (ro) — Returns the collection that provides access to the existing cut-paste features and supports the creation of new cut-paste features.
- prop `flangeFeatures`: FlangeFeatures (ro) — Returns the collection that provides access to the existing flange features.
- prop `unfoldFeatures`: UnfoldFeatures (ro) — Returns the collection that provides access to the existing unfold features.
- prop `refoldFeatures`: RefoldFeatures (ro) — Returns the collection that provides access to the existing refold features.
- prop `ruledSurfaceFeatures`: RuledSurfaceFeatures (ro) — Returns the collection that provides access to the Ruled Surface features within the component and supports the creation of new Ruled Surface features.
- prop `customFeatures`: CustomFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `untrimFeatures`: UntrimFeatures (ro) — Returns the collection that provides access to the Untrim features within the component and supports the creation of new Untrim features.
- prop `bossFeatures`: BossFeatures (ro) — Returns the collection that provides access to the boss features within the component and supports the creation of new boss features.
- prop `meshRepairFeatures`: MeshRepairFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `meshSmoothFeatures`: MeshSmoothFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `meshReduceFeatures`: MeshReduceFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `meshRemeshFeatures`: MeshRemeshFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `meshGenerateFaceGroupsFeatures`: MeshGenerateFaceGroupsFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `meshShellFeatures`: MeshShellFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `tessellateFeatures`: TessellateFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `meshCombineFeatures`: MeshCombineFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `ripFeatures`: RipFeatures (ro) — Returns the collection that provides access to the existing Rip features.
- prop `meshConvertFeatures`: MeshConvertFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `meshCombineFaceGroupsFeatures`: MeshCombineFaceGroupsFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `mergeFacesFeatures`: MergeFacesFeatures (ro) — Returns the collection object that supports the ability to merge faces.
- prop `meshSeparateFeatures`: MeshSeparateFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `meshReverseNormalFeatures`: MeshReverseNormalFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `arrangeFeatures`: ArrangeFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `volumetricCustomFeatures`: VolumetricCustomFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `volumetricModelToMeshFeatures`: VolumetricModelToMeshFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `embossFeatures`: EmbossFeatures (ro) — Returns the collection that provides access to the emboss features within the component and supports the creation of new emboss features.
- prop `hemFeatures`: HemFeatures (ro) — Returns the collection that provides access to the existing Hem features.
- prop `meshRemoveFeatures`: MeshRemoveFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `deriveFeatures`: DeriveFeatures (ro) — Returns the collection that provides access to the Derive features within the component and supports the creation of new Derive features.
- prop `cornerClosureFeatures`: CornerClosureFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `joinByBendFeatures`: JoinByBendFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `volumetricModelFeatures`: VolumetricModelFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `foldFeatures`: FoldFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `loftedFlangeFeatures`: LoftedFlangeFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `sheetMetalFilletFeatures`: SheetMetalFilletFeatures (ro) — ** This property is a preview feature and may change in future releases.
- prop `sheetMetalChamferFeatures`: SheetMetalChamferFeatures (ro) — ** This property is a preview feature and may change in future releases.

### FilletEdgeSet
The base class for the classes that define the different types of fillet edge sets.
- `deleteMe() -> bool` — Deletes the fillet edge set from the fillet.
- prop `isTangentChain`: bool (rw) — Gets and sets the Tangent chain for fillet.
- prop `continuity`: SurfaceContinuityTypes (rw) — Gets and sets the continuity of the fillet edge set.
- prop `tangencyWeight`: ModelParameter (ro) — Returns the model parameter that controls the G1 or G2 tangency weight of the fillet.

### FilletEdgeSetInput
Represents the input to define a fillet edge set.
- prop `entities`: ObjectCollection (rw) — Gets and sets the entities associated with this fillet edge set.
- prop `continuity`: SurfaceContinuityTypes (rw) — Gets and sets the continuity of the fillet edge set.
- prop `tangencyWeight`: ValueInput (rw) — Gets and sets the tangency weight for the given edge set.

### FilletEdgeSetInputs
Collection of edge sets associated with the input object that will be used to create the new fillet feature.
- `item(index: int) -> FilletEdgeSetInput` — Function that returns the specified fillet edge set input using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addConstantRadiusEdgeSet(entities: ObjectCollection, radius: ValueInput, isTangentChain: bool) -> ConstantRadiusFilletEdgeSetInput` — Adds a constant radius fillet edge set to the fillet feature input.
    - `entities`: An ObjectCollection containing the BRepEdge, BRepFace, and Feature objects to be filleted.
    - `radius`: A ValueInput object that defines the radius of the fillet.
    - `isTangentChain`: A boolean value for setting whether or not edges that are tangentially connected to the input edges (if any) will also be filleted.
- `addVariableRadiusEdgeSet(tangentEdges: ObjectCollection, startRadius: ValueInput, endRadius: ValueInput, isTangentChain: bool) -> VariableRadiusFilletEdgeSetInput` — Adds a single edge or set of tangent edges to the fillet feature input.
    - `tangentEdges`: An object collection containing a single edge or multiple edges.
    - `startRadius`: A ValueInput object that defines the starting radius of the fillet.
    - `endRadius`: A ValueInput object that defines the ending radius of the fillet.
    - `isTangentChain`: A boolean value for setting whether or not edges that are tangentially connected to the single input edge will also be filleted.
- `addChordLengthEdgeSet(entities: ObjectCollection, chordLength: ValueInput, isTangentChain: bool) -> ChordLengthFilletEdgeSetInput` — Adds a set of edges to be filleted with a chord length fillet to the fillet feature input.
    - `entities`: An ObjectCollection containing the BRepEdge, BRepFace, and Feature objects to be filleted.
    - `chordLength`: A ValueInput object that defines the chord length of the fillet.
    - `isTangentChain`: A boolean value for setting whether or not edges or faces that are tangentially connected to the input edges or faces (if any) will also be filleted.
- `addAsymmetricRadiusEdgeSet(entities: ObjectCollection, offsetOne: ValueInput, offsetTwo: ValueInput, isTangentChain: bool) -> AsymmetricFilletEdgeSetInput` — Adds an asymmetric fillet edge set to the fillet feature input.
    - `entities`: An ObjectCollection containing the BRepEdge, BRepFace, and Feature objects to be filleted.
    - `offsetOne`: A ValueInput object that defines the offset of the fillet in the first direction.
    - `offsetTwo`: A ValueInput object that defines the offset of the fillet in the second direction.
    - `isTangentChain`: A boolean value for setting whether or not edges or faces that are tangentially connected to the input edges or faces will also be filleted.
- prop `count`: int (ro) — The number of fillet edge set input objects in the collection.

### FilletEdgeSets
Collection that provides access to all of the existing fillet edge sets associated with a fillet feature.
- `item(index: int) -> FilletEdgeSet` — Function that returns the specified fillet edge set using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addConstantRadiusEdgeSet(entities: ObjectCollection, radius: ValueInput, isTangentChain: bool) -> ConstantRadiusFilletEdgeSet` — Adds a set of edges with a constant radius to this fillet feature.
    - `entities`: An ObjectCollection containing the BRepEdge, BRepFace, and Feature objects to be filleted.
    - `radius`: A ValueInput object that defines the radius of the fillet.
    - `isTangentChain`: A boolean value for setting whether or not edges that are tangentially connected to the input edges (if any) will also be filleted.
- `addVariableRadiusEdgeSet(tangentEdges: ObjectCollection, startRadius: ValueInput, endRadius: ValueInput, positions: list[ValueInput], radii: list[ValueInput], isTangentChain: bool) -> VariableRadiusFilletEdgeSet` — Adds a single edge or set of tangent edges along with variable radius information to this fillet feature.
    - `tangentEdges`: An object collection containing a single edge or multiple edges.
    - `startRadius`: A ValueInput object that defines the starting radius of the fillet.
    - `endRadius`: A ValueInput object that defines the ending radius of the fillet.
    - `positions`: An array of ValueInput objects that defines the positions of any additional radii along the edge(s).
    - `radii`: An array of ValueInput objects that define the radii at positions along the edge(s).
    - `isTangentChain`: A boolean value for setting whether or not edges that are tangentially connected to the single input edge will also be filleted.
- `addChordLengthEdgeSet(entities: ObjectCollection, chordLength: ValueInput, isTangentChain: bool) -> ChordLengthFilletEdgeSet` — Adds a set of edges with a chord length to this fillet feature.
    - `entities`: An ObjectCollection containing the BRepEdge, BRepFace, and Feature objects to be filleted.
    - `chordLength`: A ValueInput object that defines the chord length of the fillet.
    - `isTangentChain`: A boolean value for setting whether or not edges that are tangentially connected to the input edges (if any) will also be filleted.
- `addAsymmetricRadiusEdgeSet(entities: ObjectCollection, offsetOne: ValueInput, offsetTwo: ValueInput, isTangentChain: bool) -> AsymmetricFilletEdgeSet` — Adds an asymmetric fillet edge set to the fillet feature.
    - `entities`: An ObjectCollection containing the BRepEdge, BRepFace, and Feature objects to be filleted.
    - `offsetOne`: A ValueInput object that defines the offset distance of the fillet in the first direction.
    - `offsetTwo`: A ValueInput object that defines the offset distance of the fillet in the second direction.
    - `isTangentChain`: A boolean value for setting whether or not edges or faces that are tangentially connected to the input edges or faces will also be filleted.
- prop `count`: int (ro) — The number of fillet edge sets in the collection.

### FilletFeatureInput
This class defines the methods and properties that pertain to the definition of a fillet feature.
- prop `isRollingBallCorner`: bool (rw) — Gets and sets if a rolling ball or setback solution is to be used in any corners.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `edgeSetInputs`: FilletEdgeSetInputs (ro) — Gets the FilletEdgeSetInputs object that provides support to create the various types of edge sets that will be used to create the fillet.

### FilletFeatures
Collection that provides access to all of the existing fillet features in a component and supports the ability to create new fillet features.
- `item(index: int) -> FilletFeature` — Function that returns the specified fillet feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput() -> FilletFeatureInput` — Creates a FilletFeatureInput object.
- `add(input: FilletFeatureInput) -> FilletFeature` — Creates a new fillet feature.
    - `input`: A FilletFeatureInput object that defines the desired fillet.
- `itemByName(name: str) -> FilletFeature` — Function that returns the specified fillet feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createFullRoundFilletInput() -> FullRoundFilletFeatureInput` — Creates a FullRoundFilletFeatureInput object.
- `addFullRoundFillet(input: FullRoundFilletFeatureInput) -> FilletFeature` — Creates a new full round fillet feature.
    - `input`: A FullRoundFilletFeatureInput object that defines the desired fillet.
- `createRuleFilletInput() -> RuleFilletFeatureInput` — Creates a RuleFilletFeatureInput object.
- `addRuleFillet(input: RuleFilletFeatureInput) -> FilletFeature` — Creates a new rule fillet feature.
    - `input`: A RuleFilletFeatureInput object that defines the desired fillet.
- prop `count`: int (ro) — The number of fillet features in the collection.

### HoleFeatureInput
This class defines the methods and properties that pertain to the definition of a hole feature.
- `setPositionByPoint(planarEntity: Base, point: Base) -> bool` — Defines the position of a the hole using a point.
    - `planarEntity`: The planar BRepFace or ConstructionPlane object that defines the orientation of the hole.
    - `point`: A Point3D object or vertex that defines the position of the hole.
- `setPositionAtCenter(planarEntity: Base, centerEdge: BRepEdge) -> bool` — Defines the position of the hole at the center of a circular or elliptical edge of the face.
    - `planarEntity`: The planar BRepFace or ConstructionPlane object that defines the orientation of the hole.
    - `centerEdge`: A circular or elliptical edge whose center point will be the position of the hole.
- `setPositionBySketchPoint(sketchPoint: SketchPoint) -> bool` — Defines the position and orientation of the hole using a sketch point.
    - `sketchPoint`: The sketch point that defines the position of the hole.
- `setPositionByPlaneAndOffsets(planarEntity: Base, point: Point3D, edgeOne: BRepEdge, offsetOne: ValueInput, edgeTwo: BRepEdge = None, offsetTwo: ValueInput = None) -> bool` — Defines the orientation of the hole using a planar face or construction plane.
    - `planarEntity`: The planar BRepFace or ConstructionPlane object that defines the orientation of the hole.
    - `point`: A Point3D object that defines the approximate initial position of the hole.
    - `edgeOne`: A linear BRepEdge object that the position of the hole will be measured from.
    - `offsetOne`: A ValueInput object that defines the offset distance from edgeOne.
    - `edgeTwo`: You can optionally define a second edge and offset to specify the position of the hole.
    - `offsetTwo`: If edgeTwo is defined, you must provide this argument which is a ValueInput object that defines the offset from the edgeTwo.
- `setPositionOnEdge(planarEntity: Base, edge: BRepEdge, position: HoleEdgePositions) -> bool` — Defines the position and orientation of the hole to be on the start, end or center of an edge.
    - `planarEntity`: The planar BRepFace or ConstructionPlane object that defines the orientation of the hole and start of the hole.
    - `edge`: The edge to position the hole on.
    - `position`: The position along the edge to place the hole.
- `setDistanceExtent(distance: ValueInput) -> bool` — Defines the depth of the hole using a specified distance.
    - `distance`: The depth of the hole.
- `setAllExtent(direction: ExtentDirections) -> bool` — Defines the extent of the hole to be through-all.
    - `direction`: The direction of the hole relative to the normal of the sketch plane.
- `setOneSideToExtent(toEntity: Base, matchShape: bool, directionHint: Vector3D = None) -> bool` — Sets the extent of the hole to be from the sketch plane to the specified "to" face.
    - `toEntity`: The entity that defines the "to" extent.
    - `matchShape`: Indicates if the hole is not contained on the face that the hole should match the shape of the entity as if it extended beyond its current boundaries.
    - `directionHint`: Specifies the direction of the hole.
- `setPositionBySketchPoints(sketchPoints: ObjectCollection) -> bool` — Defines the position and orientation of the hole using a set of sketch points.
    - `sketchPoints`: A collection of sketch points that defines the positions of the holes.
- `setToSimpleHole() -> bool` — This property sets the hole's tap to be "simple", which means that it will not have any tap and will be a simple hole.
- `setToClearanceHole(clearanceHoleInfo: ClearanceHoleInfo) -> bool` — Sets the hole to be a clearance hole of the size specified by the ClearanceHoleInfo object.
    - `clearanceHoleInfo`: The ClearanceHoleInfo object that specifies the size of the clearance hole.
- `setToTappedHole(threadInfo: ThreadInfo) -> bool` — Sets the hole to be a straight or tapered tapped hole of the size specified by the ThreadInfo object.
    - `threadInfo`: The ThreadInfo object that specifies the thread to use for the tapped hole.
- `setLengthAndOffset(length: ValueInput, offset: ValueInput) -> bool` — Sets the length and offset of the thread of a tapped hole.
    - `length`: Sets the length of the thread.
    - `offset`: Sets the offset of the thread from the start of the hole.
- prop `tipAngle`: ValueInput (rw) — Gets the ValueInput object that defines the angle of the tip of the hole.
- prop `isDefaultDirection`: bool (rw) — Gets or sets if the hole goes in the default direction or is reversed.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the Hole is created based on geometry (e.g.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the hole.
- prop `holeTapType`: HoleTapTypes (ro) — Returns the current type of tap associated with this hole.
- prop `isModeled`: bool (rw) — Gets and sets if the thread is physical or cosmetic thread.
- prop `isFullLength`: bool (rw) — Gets and sets if this thread is the full length of the hole.
- prop `threadLength`: ValueInput (ro) — Gets the thread length when the isFullLength property is False.
- prop `threadOffset`: ValueInput (ro) — Gets the thread offset when the isFullLength property is False.

### HoleFeatures
Collection that provides access to all of the existing hole features in a component and supports the ability to create new hole features.
- `item(index: int) -> HoleFeature` — Function that returns the specified hole feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createSimpleInput(holeDiameter: ValueInput) -> HoleFeatureInput` — Creates a HoleFeatureInput object that defines a simple hole (a single diameter).
    - `holeDiameter`: A ValueInput object that defines the diameter of the hole.
- `createCounterboreInput(holeDiameter: ValueInput, counterboreDiameter: ValueInput, counterboreDepth: ValueInput) -> HoleFeatureInput` — Creates a HoleFeatureInput object that defines a counterbore hole.
    - `holeDiameter`: A ValueInput object that defines the diameter of the hole.
    - `counterboreDiameter`: A ValueInput object that defines the counterbore diameter of the hole.
    - `counterboreDepth`: A ValueInput object that defines the counterbore depth of the hole.
- `createCountersinkInput(holeDiameter: ValueInput, countersinkDiameter: ValueInput, countersinkAngle: ValueInput) -> HoleFeatureInput` — Creates a HoleFeatureInput object that defines a countersink hole.
    - `holeDiameter`: A ValueInput object that defines the diameter of the hole.
    - `countersinkDiameter`: A ValueInput object that defines the diameter of the countersink.
    - `countersinkAngle`: A ValueInput object that defines the angle of the countersink.
- `add(input: HoleFeatureInput) -> HoleFeature` — Creates a new hole feature based on the information provided by a HoleFeatureInput object.
    - `input`: The HoleFeatureInput object that defines the hole you want to create.
- `itemByName(name: str) -> HoleFeature` — Function that returns the specified hole feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of hole features in the collection.

### HolePositionDefinition
The base class for the classes that define how a hole can be positioned.

### LoftCenterLineOrRail
Represent a centerline or a single rail used by a loft feature.
- `deleteMe() -> bool` — Deletes the centerline or rail.
- prop `isCenterLine`: bool (ro) — Indicates if this object is a loft centerline (true) or a rail (false).
- prop `entity`: Base (rw) — Gets and sets the entity that defines the centerline or rail.
- prop `edgeCondition`: LoftRailEdgeConditions (rw) — Gets and sets the edge condition for this rail.

### LoftCenterLineOrRails
Defines a single centerline or one or more rails for a loft feature.
- `item(index: int) -> LoftCenterLineOrRail` — Function that returns the specified LoftCenterLineOrRail using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addCenterLine(entity: Base) -> LoftCenterLineOrRail` — Adds a centerline.
    - `entity`: The entity that defines the center line.
- `addRail(entity: Base) -> LoftCenterLineOrRail` — Add a rail to the loft definition.
    - `entity`: The entity that defines the rail.
- prop `count`: int (ro) — The number of centerlines or rails in the collection.
- prop `isCenterLine`: bool (ro) — Indicates if a centerline or rails are currently defined.

### LoftedFlangeFeatureInput
** This class is a preview feature and may change in future releases.
- `setFacetControlByChordTolerance(chordTolerance: ValueInput) -> bool` — Sets the facet control to chord tolerance, which limits the maximum distance between the true curved surface and the faceted approximation.
    - `chordTolerance`: The maximum allowable chord tolerance distance.
- `setFacetControlByFacetAngle(facetAngle: ValueInput) -> bool` — Sets the facet control to facet angle, which limits the maximum angle between adjacent facet normals.
    - `facetAngle`: The maximum allowable angle between adjacent facet normals.
- `setFacetControlByFacetDistance(facetDistance: ValueInput) -> bool` — Sets the facet control to facet distance, which limits the maximum length of any individual facet edge.
    - `facetDistance`: The maximum allowable facet edge length.
- `setFacetControlByFacetNumber(facetNumber: ValueInput) -> bool` — Sets the facet control to a fixed number of facets along the transition.
    - `facetNumber`: The number of facets.
- prop `profiles`: list[Profile] (rw) — Gets and sets the ordered array of open profiles that define the cross-sections of the lofted flange.
- prop `orientation`: FlangeOrientations (rw) — Gets and sets the orientation of the lofted flange, defining on which side of the profile planes the material thickness is applied.
- prop `formingType`: LoftedFlangeFormingTypes (rw) — Gets and sets the forming type for the lofted flange, which controls how the sheet metal is physically formed between the profiles.
- prop `facetControlType`: LoftedFlangeFacetControlTypes (ro) — Gets the facet control type currently defined for the lofted flange.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed when creating the lofted flange.

### LoftedFlangeFeatures
** This class is a preview feature and may change in future releases.
- `item(index: int) -> LoftedFlangeFeature` — Function that returns the specified lofted flange feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> LoftedFlangeFeature` — Function that returns the specified lofted flange feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInput(profiles: list[Profile]) -> LoftedFlangeFeatureInput` — Creates a LoftedFlangeFeatureInput object.
    - `profiles`: An ordered array of exactly two profiles that define the cross-sections of the lofted flange.
- `add(input: LoftedFlangeFeatureInput) -> LoftedFlangeFeature` — Creates a new lofted flange feature.
    - `input`: A LoftedFlangeFeatureInput object that defines the desired lofted flange.
- prop `count`: int (ro) — The number of lofted flange features in the collection.

### LoftEndCondition
The base class for all loft end conditions.
- prop `parentLoftSection`: LoftSection (ro) — Returns the parent loft section.

### LoftFeatureInput
This object defines the all of the input necessary to create a loft feature.
- prop `loftSections`: LoftSections (ro) — The set of sections, (or profiles as they're referred to in the user-interface), that the loft will pass through.
- prop `centerLineOrRails`: LoftCenterLineOrRails (ro) — The single centerline or set of rails that define the shape of the loft.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the loft.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the loft is created based on geometry (e.g.
- prop `isSolid`: bool (rw) — Specifies if the loft should be created as a solid or surface.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `isClosed`: bool (rw) — Specifies if the loft closes back on itself.
- prop `isTangentEdgesMerged`: bool (rw) — Specifies if the loft will keep or merge tangent edges.
- prop `startLoftEdgeAlignment`: LoftEdgeAlignments (rw) — Specifies the start edge alignment option for the loft feature.
- prop `endLoftEdgeAlignment`: LoftEdgeAlignments (rw) — Specifies the end edge alignment option for the loft feature.

### LoftFeatures
Collection that provides access to all of the existing loft features in a design.
- `item(index: int) -> LoftFeature` — Function that returns the specified loft feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> LoftFeature` — Function that returns the specified loft feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInput(operation: FeatureOperations) -> LoftFeatureInput` — Creates a LoftFeatureInput object.
    - `operation`: The feature operation to perform.
- `add(input: LoftFeatureInput) -> LoftFeature` — Creates a new loft feature.
    - `input`: A LoftFeatureInput object that defines the desired loft feature.
- prop `count`: int (ro) — The number of loft features in the collection.

### LoftSection
A single loft section.
- `deleteMe() -> bool` — Deletes this LoftSection.
- `reorder(newIndex: int) -> bool` — Repositions this section so that it has the new index specified.
    - `newIndex`: The new index value.
- `setFreeEndCondition() -> bool` — Sets the end condition to be a "Free" end condition.
- `setDirectionEndCondition(angle: ValueInput = None, weight: ValueInput = None) -> bool` — Sets the end condition to be defined by a direction and weight.
    - `angle`: Input ValueInput object that specifies the direction by using an angle.
    - `weight`: Input ValueInput object that defines the weight or the amount of influence of end condition on the loft.
- `setTangentEndCondition(weight: ValueInput) -> bool` — Sets the end condition to be tangent to the adjacent face.
    - `weight`: Input ValueInput object that defines the weight or the amount of influence of end condition on the loft.
- `setSmoothEndCondition(weight: ValueInput) -> bool` — Sets the end condition to be smooth to the adjacent face.
    - `weight`: Input ValueInput object that defines the weight or the amount of influence of end condition on the loft.
- `setPointSharpEndCondition() -> bool` — Sets the end condition to be sharp where the section is a point.
- `setPointTangentEndCondition(weight: ValueInput) -> bool` — Set the end condition to a tangent condition in the case where the section is a point.
    - `weight`: Input ValueInput object that defines the weight or the amount of influence of end condition on the loft.
- prop `entity`: Base (rw) — Get and sets the entity that defines the section of the loft.
- prop `index`: int (ro) — The position of this LoftSection within the collection.
- prop `endCondition`: LoftEndCondition (ro) — Returns the current end condition.

### LoftSections
The set of two or more sections used to define the shape of the loft.
- `item(index: int) -> LoftSection` — Function that returns the specified LoftSection using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(entity: Base) -> LoftSection` — Adds a new section to the loft.
    - `entity`: Specifies the BRepFace, Profile, Path, SketchPoint, ConstructionPoint, or an ObjectCollection containing a contiguous set of Profile objects that defines the section.
- prop `count`: int (ro) — The number of LoftSections in the collection.

### MirrorFeatureInput
This class defines the methods and properties that pertain to the definition of a mirror feature.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the input entities that are mirrored.
- prop `mirrorPlane`: Base (rw) — Gets and sets the mirror plane.
- prop `patternComputeOption`: PatternComputeOptions (rw) — Gets and sets the compute option when mirroring features.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `isCombine`: bool (rw) — Gets and sets whether the mirrored bodies should be combined with the original bodies.
- prop `stitchTolerance`: ValueInput (rw) — Gets and sets the ValueInput object that defines the Stitching Tolerance (length) to use when doing a mirror and combine for surface bodies.

### MirrorFeatures
Collection that provides access to all of the existing mirror features in a component and supports the ability to create new mirror features.
- `item(index: int) -> MirrorFeature` — Function that returns the specified mirror feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputEntities: ObjectCollection, mirrorPlane: Base) -> MirrorFeatureInput` — Creates a MirrorFeatureInput object.
    - `inputEntities`: An ObjectCollection of the entities to mirror.
    - `mirrorPlane`: Input planar entity that defines the mirror plane.
- `add(input: MirrorFeatureInput) -> MirrorFeature` — Creates a new mirror feature.
    - `input`: A MirrorFeatureInput object that defines the desired mirror.
- `itemByName(name: str) -> MirrorFeature` — Function that returns the specified mirror feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of mirror features in the collection.

### ModelParameters
Provides access to the Model Parameters within a component.
- `item(index: int) -> ModelParameter` — Function that returns the specified Model Parameter using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> ModelParameter` — Function that returns the specified Model Parameter using the name of the parameter as it is displayed in the parameters dialog.
    - `name`: The name of the Model Parameter as it is displayed in the parameters dialog
- prop `count`: int (ro) — Returns the number of parameters in the collection.
- prop `component`: Component (ro) — Returns the component that owns the Model Parameters collection

### MoveFeatureDefinition
A Base class to return the information used to define a Move feature.
- prop `parentMoveFeature`: MoveFeature (ro) — Returns the parent MoveFeature object

### MoveFeatureInput
This class defines the methods and properties that pertain to the definition of a move feature.
- `defineAsFreeMove(transform: Matrix3D) -> bool` — This method will define a move feature whose translation and orientation is defined using a transformation matrix.
    - `transform`: The transformation matrix that defines the transform to apply.
- `defineAsTranslateXYZ(xDistance: ValueInput, yDistance: ValueInput, zDistance: ValueInput, isDesignSpace: bool) -> bool` — This method will define a move feature that defines a translation in X, Y, and Z.
    - `xDistance`: A ValueInput object that defines the offset in the X direction.
    - `yDistance`: A ValueInput object that defines the offset in the Y direction.
    - `zDistance`: A ValueInput object that defines the offset in the Z direction.
    - `isDesignSpace`: Defines if the translation is defined with respect to the design or component space.
- `defineAsTranslateAlongEntity(linearEntity: Base, distance: ValueInput) -> bool` — This method will define a move feature that defines a translation along a specified entity.
    - `linearEntity`: A linear entity that defines the direction of the move.
    - `distance`: A ValueInput object that defines the offset distance.
- `defineAsRotate(axisEntity: Base, angle: ValueInput) -> bool` — This method defines a move feature that is described by an axis and rotation angle.
    - `axisEntity`: A linear entity that defines the axis of rotation.
    - `angle`: A ValueInput object that defines the rotation angle.
- `defineAsPointToPoint(originPoint: Base, targetPoint: Base) -> bool` — This method defines a move feature described by a translation from one point to another.
    - `originPoint`: The first point that defines the start position of the move.
    - `targetPoint`: The second point that defines the direction and distance of the move.
- `defineAsPointToPosition(point: Base, xDistance: ValueInput, yDistance: ValueInput, zDistance: ValueInput, isDesignSpace: bool) -> bool` — This method defines a move feature described by a point and an offset.
    - `point`: An entity that defines a point in space.
    - `xDistance`: A ValueInput object that defines the offset in the X direction.
    - `yDistance`: A ValueInput object that defines the offset in the Y direction.
    - `zDistance`: A ValueInput object that defines the offset in the Z direction.
    - `isDesignSpace`: Defines if the translation is defined with respect to the design or component space.
- prop `inputEntities`: ObjectCollection (rw) — An ObjectCollection containing the objects to move.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### MoveFeatures
Collection that provides access to all of the existing move features in a component and supports the ability to create new move features.
- `item(index: int) -> MoveFeature` — Function that returns the specified move feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(input: MoveFeatureInput) -> MoveFeature` — Creates a new move feature.
    - `input`: A MoveFeatureInput object that defines the desired move feature.
- `itemByName(name: str) -> MoveFeature` — Function that returns the specified move feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInput2(inputEntities: ObjectCollection) -> MoveFeatureInput` — Creates a MoveFeatureInput object.
    - `inputEntities`: An ObjectCollection containing the objects to move.
- prop `count`: int (ro) — The number of move features in the collection.

### OffsetConstraintInput
Used to define the inputs needed to create an offset constraint.
- prop `curves`: list[SketchCurve] (rw) — Gets and sets an array of SketchCurve objects that defines the connected curves that will be offset.
- prop `offset`: ValueInput (rw) — Gets and sets the value that defines the offset.
- prop `dimensionPoint`: Point3D (rw) — A location on one of the curves where the offset dimension will be created.
- prop `isTopologyMatched`: bool (rw) — Specifies if the offset curves must match the topology of the original curves.

### OffsetFacesFeatureInput
Object that represents an existing Offset Faces feature in a design.
- prop `faces`: list[BRepFace] (rw) — An array of BRepFace objects you want to offset.
- prop `distance`: ValueInput (rw) — The distance of the offset.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### OffsetFacesFeatures
Collection that provides access to all of the existing Offset Faces features in a design.
- `item(index: int) -> OffsetFacesFeature` — Function that returns the specified Offset Face feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> OffsetFacesFeature` — Function that returns the specified Offset Face feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInput(faces: list[BRepFace], distance: ValueInput) -> OffsetFacesFeatureInput` — Creates an OffsetFacesFeatureInput object.
    - `faces`: An array of BRepFace objects to offset.
    - `distance`: The distance of the offset.
- `add(input: OffsetFacesFeatureInput) -> OffsetFacesFeature` — Creates a new offset feature.
    - `input`: An OffsetFacesFeatureInput object that defines the desired offset faces feature.
- prop `count`: int (ro) — The number of Offset Face features in the collection.

### OffsetFeatureInput
This class defines the methods and properties that pertain to the definition of an offset feature.
- prop `entities`: ObjectCollection (rw) — An ObjectCollection containing the BRepFace objects being offset.
- prop `isChainSelection`: bool (rw) — Get and sets whether faces that are tangentially connected to the input faces will be included in the offset.
- prop `distance`: ValueInput (rw) — Gets and sets the ValueInput object that defines the offset distance.
- prop `operation`: FeatureOperations (rw) — Gets and sets the feature operation to perform.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `offsetType`: OffsetTypes (rw) — The offset type used when creating an offset.

### OffsetFeatures
Collection that provides access to all of the existing Offset features in a component and supports the ability to create new Offset features.
- `item(index: int) -> OffsetFeature` — Function that returns the specified offset feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(entities: ObjectCollection, distance: ValueInput, operation: FeatureOperations, isChainSelection: bool = True) -> OffsetFeatureInput` — Creates an OffsetFeatureInput object.
    - `entities`: An ObjectCollection containing the BRepFace objects to offset.
    - `distance`: ValueInput object that defines the offset distance.
    - `operation`: The feature operation to perform.
    - `isChainSelection`: A boolean value for setting whether or not faces that are tangentially connected to the input faces (if any) will be included in the offset.
- `add(input: OffsetFeatureInput) -> OffsetFeature` — Creates a new offset feature.
    - `input`: A FeatureInput object that defines the desired offset feature.
- `itemByName(name: str) -> OffsetFeature` — Function that returns the specified offset feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of Offset features in the collection.

### Parameter
The base class Parameter object that can represent model or user parameters.
- prop `value`: float (rw) — Gets and sets the real value (a double) of the parameter in database units.
- prop `expression`: str (rw) — Gets and sets the expression used to calculate the value of the parameter.
- prop `name`: str (rw) — Gets and sets the name of the parameter.
- prop `unit`: str (ro) — The unit type associated with this parameter.
- prop `comment`: str (rw) — The comment associated with this parameter.
- prop `isFavorite`: bool (rw) — Gets and sets whether this parameter is included in the Favorites list in the parameters dialog
- prop `dependentParameters`: ParameterList (ro) — Returns a list of parameters that are dependent on this parameter as a result of this parameter being referenced in their equation.
- prop `isDeletable`: bool (ro) — Gets if this parameter can be deleted.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this face.
- prop `entityToken`: str (ro) — Returns a token for the Parameter object.
- prop `dependencyParameters`: ParameterList (ro) — Returns a list of parameters that this parameter is dependent on.
- prop `textValue`: str (rw) — Gets and sets the value of the parameter when it is a text parameter.
- prop `valueType`: ParameterValueTypes (ro) — Returns the type of value this parameter is.

### ParameterList
Transient object used to pass a set of parameters.
- `create() -> ParameterList` — Creates a parameter list that the client can use for various purposes.
- `item(index: int) -> Parameter` — Function that returns the specified parameter using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> Parameter` — Returns the specified parameter using the name of the parameter as it is displayed in the parameters dialog.
    - `name`: The name of the parameter as it is displayed in the parameters dialog.
- `add(parameter: Parameter) -> bool` — Adds a parameter to the list.
    - `parameter`: The existing parameter to add to the list
- `removeByIndex(index: int) -> bool` — Method that removes a parameter from the list using the index of the item in the list Will fail if the list is read only.
    - `index`: The index of the parameter to be removed from the list
- `removeByItem(item: Parameter) -> bool` — Method that removes a parameter from the list by specifying the parameter (item) to remove item : The parameter item to remove from the list Returns true if successful.
    - `item`: The parameter item to remove from the list
- `find(parameter: Parameter, startIndex: int = 0) -> int` — Finds the specified parameter in the list.
    - `parameter`: The parameter to find
    - `startIndex`: the index in the list to start the search from
- `contains(parameter: Parameter) -> bool` — Indicates whether or not ParameterList collection contains a specified parameter parameter : The parameter to look for in the list Returns true if list contains the specified parameter
    - `parameter`: The parameter to look for in the list
- prop `count`: int (ro) — Returns the number of parameters in the collection.
- prop `isReadOnly`: bool (ro) — Indicates if the list is read-only Some lists returned by API calls (instead of lists created by the user) are read only.

### PatchFeatureInput
This class defines the methods and properties that pertain to the definition of a patch feature.
- `setContinuity(continuity: list[int], weight: list[float], isContinuityDirectionFlipped: list[bool]) -> bool` — Sets the continuity to use for each edge in the boundary.
    - `continuity`: An array whose size of the number of B-Rep edges in the boundary.
    - `weight`: An array whose size is the number of B-Rep edges in the boundary.
    - `isContinuityDirectionFlipped`: An array whose size is the number of B-Rep edges in the boundary.
- `getContinuity() -> tuple[bool, list[BRepEdge], list[int], list[float], list[bool]]` — Gets the continuity used for each edge in the boundary.
    - `edges`: Output array containing all of the BRepEdge objects in the boundary.
    - `continuity`: Output array the same size as the edges array that defines the continuity to apply to the edge in the same index in the edges array.
    - `weight`: Output array the same size as the edges array that defines the weight applied to the edge in the same index in the edges array.
    - `isContinuityDirectionFlipped`: Output array the same size as the edges array that defines which of the two faces the edge connects to is used in computing the continuity direction.
- prop `boundaryCurve`: Base (rw) — Gets and sets the input geometry that will be used to define the boundary.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the patch feature.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `creationOccurrence`: Occurrence (rw) — For geometry to be transformed correctly, an Occurrence for creation needs to be specified when the Patch feature is created based on geometry (e.g., a profile, edges, faces) in another component AND (the Patch feature) …
- prop `interiorRailsAndPoints`: ObjectCollection (rw) — Gets and sets any interior curves or points the patch should fit through.
- prop `isGroupEdges`: bool (rw) — Gets and sets if the edges in the boundary curve are treated as a group, and they all use the same continuity.
- prop `groupContinuity`: SurfaceContinuityTypes (rw) — Gets and sets the type of surface continuity to use for all edges when the isGroupEdges property is true.
- prop `groupWeight`: float (rw) — Gets and sets the weight to use for all edges when the isGroupEdges property is true.
- prop `groupIsContinuityDirectionFlipped`: bool (rw) — Gets and sets the continuity direction for all edges when the isGroupEdges property is true.

### PatchFeatures
Collection that provides access to all of the existing Patch features in a component and supports the ability to create new Patch features.
- `item(index: int) -> PatchFeature` — Function that returns the specified patch feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> PatchFeature` — Function that returns the specified patch feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInput(boundaryCurve: Base, operation: FeatureOperations) -> PatchFeatureInput` — Creates a PatchFeatureInput object.
    - `boundaryCurve`: Defines the input geometry that will be used to define the boundary.
    - `operation`: The feature operation to perform.
- `add(input: PatchFeatureInput) -> PatchFeature` — Creates a new patch feature.
    - `input`: A PatchFeatureInput object that defines the desired patch feature.
- prop `count`: int (ro) — The number of Patch features in the collection.

### PathPatternFeatureInput
This class defines the methods and properties that pertain to the definition of a path pattern feature.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the input entities.
- prop `path`: Path (rw) — Gets and sets the path to create the pattern on path.
- prop `quantity`: ValueInput (rw) — Gets and sets quantity of the elements.
- prop `distance`: ValueInput (rw) — Gets and sets the distance.
- prop `startPoint`: float (rw) — Gets and sets the start point on the path to count the distance.
- prop `isFlipDirection`: bool (rw) — Gets and sets if flip the direction from start point.
- prop `patternDistanceType`: PatternDistanceType (rw) — Gets and sets how the distance between elements is computed.
- prop `isSymmetric`: bool (rw) — Gets and sets if the pattern is in one direction or symmetric.
- prop `isOrientationAlongPath`: bool (rw) — Gets and sets if the orientation is along path.
- prop `patternComputeOption`: PatternComputeOptions (rw) — Gets and sets the compute option when patterning features.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### PathPatternFeatures
Collection that provides access to all of the existing path pattern features in a component and supports the ability to create new path pattern features.
- `item(index: int) -> PathPatternFeature` — Function that returns the specified path pattern feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputEntities: ObjectCollection, path: Path, quantity: ValueInput, distance: ValueInput, patternDistanceType: PatternDistanceType) -> PathPatternFeatureInput` — Creates a PathPatternFeatureInput object.
    - `inputEntities`: An ObjectCollection of the entities to pattern.
    - `path`: The Path object that represents a single set of connected curves along which to drive the pattern.
    - `quantity`: Specifies the number of instances in the first direction.
    - `distance`: Specifies the distance.
    - `patternDistanceType`: Specifies how the distance between elements is computed.
- `add(input: PathPatternFeatureInput) -> PathPatternFeature` — Creates a new path pattern feature.
    - `input`: A PathPatternFeatureInput object that defines the desired path pattern.
- `itemByName(name: str) -> PathPatternFeature` — Function that returns the specified path pattern feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of path pattern features in the collection.

### PipeFeatureInput
This class defines the methods and properties that pertain to the definition of a Pipe feature.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the Pipe.
- prop `path`: Path (rw) — Gets and sets the path to create the Pipe.
- prop `sectionType`: PipeSectionTypes (rw) — Gets and sets the section type of the Pipe.
- prop `sectionSize`: ValueInput (rw) — Gets and sets the section size of the Pipe.
- prop `isHollow`: bool (rw) — Specifies if the Pipe is hollow or not.
- prop `sectionThickness`: ValueInput (rw) — Gets and sets the section thickness of the Pipe.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the Pipe is created based on geometry (e.g.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `distanceOne`: ValueInput (rw) — Gets and sets the distance for the pipe created while following the path given as input, in the same order.
- prop `distanceTwo`: ValueInput (rw) — Gets and sets the distance for the pipe created while following the reversed path given as input.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.

### PipeFeatures
Collection that provides access to all of the existing Pipe features in a design.
- `item(index: int) -> PipeFeature` — Function that returns the specified Pipe feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> PipeFeature` — Function that returns the specified Pipe feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInput(path: Path, operation: FeatureOperations) -> PipeFeatureInput` — Creates a PipeFeatureInput object for defining a simple Pipe feature with only a path.
    - `path`: The path to create the Pipe.
    - `operation`: The feature operation to perform.
- `add(input: PipeFeatureInput) -> PipeFeature` — Creates a new Pipe feature.
    - `input`: A PipeFeatureInput object that defines the desired Pipe.
- prop `count`: int (ro) — The number of Pipe features in the collection.

### RectangularPatternConstraintInput
Used to define the inputs need to create a rectangular pattern in a sketch.
- `setDirectionOne(directionOneEntity: SketchLine, quantityOne: ValueInput, distanceOne: ValueInput) -> bool` — Sets all of the input required to define the pattern in the first direction.
    - `directionOneEntity`: Specifies the SketchLine object used to define the first direction entity.
    - `quantityOne`: Specifies the number of instances in the first direction.
    - `distanceOne`: Specifies the distance in the first direction.
- `setDirectionTwo(directionTwoEntity: SketchLine, quantityTwo: ValueInput, distanceTwo: ValueInput) -> bool` — Sets all of the input required to define the pattern in the second direction.
    - `directionTwoEntity`: Specifies the SketchLine object used to define the second direction entity.
    - `quantityTwo`: Specifies the number of instances in the second direction.
    - `distanceTwo`: Specifies the distance in the second direction.
- prop `entities`: list[SketchEntity] (rw) — Gets and sets the entities to pattern.
- prop `directionOneEntity`: SketchLine (rw) — Defines the first direction of the pattern.
- prop `directionTwoEntity`: SketchLine (rw) — Defines the second direction of the pattern.
- prop `quantityOne`: ValueInput (rw) — Gets and sets the number of instances in the first direction.
- prop `quantityTwo`: ValueInput (rw) — Gets and sets the number of instances in the second direction.
- prop `distanceOne`: ValueInput (rw) — Gets and sets the distance in the first direction.
- prop `distanceTwo`: ValueInput (rw) — Gets and sets the distance in the second direction.
- prop `isSymmetricInDirectionOne`: bool (rw) — Gets and sets if the pattern in direction one is in one direction or is symmetric.
- prop `isSymmetricInDirectionTwo`: bool (rw) — Gets and sets if the pattern in direction two is in one direction or is symmetric.
- prop `distanceType`: PatternDistanceType (rw) — Gets and sets how the distance between elements is computed.
- prop `isSuppressed`: list[bool] (rw) — Specifies which, if any, instances of the pattern are suppressed.

### RectangularPatternFeatureInput
This class defines the methods and properties that pertain to the definition of a rectangular pattern feature.
- `setDirectionTwo(directionTwoEntity: Base, quantityTwo: ValueInput, distanceTwo: ValueInput) -> bool` — Sets all of the input required to define the pattern in the second direction.
    - `directionTwoEntity`: Specifies the entity used to define the second direction entity.
    - `quantityTwo`: Specifies the number of instances in the second direction.
    - `distanceTwo`: Specifies the distance in the second direction.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the input entities.
- prop `directionOneEntity`: Base (rw) — Gets and sets the first direction entity.
- prop `directionTwoEntity`: Base (rw) — Gets and sets the second direction entity.
- prop `quantityOne`: ValueInput (rw) — Gets and sets the number of instances in the first direction.
- prop `quantityTwo`: ValueInput (rw) — Gets and sets the number of instances in the second direction.
- prop `distanceOne`: ValueInput (rw) — Gets and sets the distance in the first direction.
- prop `distanceTwo`: ValueInput (rw) — Gets and sets the distance in the second direction.
- prop `directionOne`: Vector3D (ro) — Returns a Vector3D indicating the positive direction of direction one.
- prop `directionTwo`: Vector3D (ro) — Returns a Vector3D indicating the positive direction of direction two.
- prop `isSymmetricInDirectionOne`: bool (rw) — Gets and sets if the pattern in direction one is in one direction or symmetric.
- prop `isSymmetricInDirectionTwo`: bool (rw) — Gets and sets if the pattern in direction two is in one direction or symmetric.
- prop `patternDistanceType`: PatternDistanceType (rw) — Gets and sets how the distance between elements is computed.
- prop `patternComputeOption`: PatternComputeOptions (rw) — Gets and sets the compute option when patterning features.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### RectangularPatternFeatures
Collection that provides access to all of the existing rectangular pattern features in a component and supports the ability to create new rectangular pattern features.
- `item(index: int) -> RectangularPatternFeature` — Function that returns the specified rectangular pattern feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputEntities: ObjectCollection, directionOneEntity: Base, quantityOne: ValueInput, distanceOne: ValueInput, patternDistanceType: PatternDistanceType) -> RectangularPatternFeatureInput` — Creates a RectangularPatternFeatureInput object.
    - `inputEntities`: An ObjectCollection of the entities to pattern.
    - `directionOneEntity`: Specifies the entity used to define the first direction entity.
    - `quantityOne`: Specifies the number of instances in the first direction.
    - `distanceOne`: Specifies the distance in the first direction.
    - `patternDistanceType`: Specifies how the distance between elements is computed.
- `add(input: RectangularPatternFeatureInput) -> RectangularPatternFeature` — Creates a new rectangular pattern feature.
    - `input`: A RectangularPatternFeatureInput object that defines the desired rectangular pattern.
- `itemByName(name: str) -> RectangularPatternFeature` — Function that returns the specified rectangular pattern feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of rectangular pattern features in the collection.

### RemoveFeatures
Collection that provides access to all of the existing Remove features in a component and supports the ability to create new Remove features.
- `item(index: int) -> RemoveFeature` — Function that returns the specified Remove feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> RemoveFeature` — Function that returns the specified remove feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `add(itemToRemove: Base) -> RemoveFeature` — Creates a new Remove feature.
    - `itemToRemove`: A single body (solid or surface) or component occurrence to remove.
- prop `count`: int (ro) — The number of Remove features in the collection.

### ReplaceFaceFeatureInput
This class defines the methods and properties that pertain to the definition of a replace face feature.
- prop `sourceFaces`: ObjectCollection (rw) — Gets and sets the entities that define the source faces to perform replace.
- prop `targetFaces`: Base (rw) — Gets and sets the entities that define the target faces.
- prop `isTangentChain`: bool (rw) — Gets and sets if any faces that are tangentially connected to any of the input faces will also be included in setting InputEntities.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### ReplaceFaceFeatures
Collection that provides access to all of the existing replace face features in a component and supports the ability to create new replace face features.
- `item(index: int) -> ReplaceFaceFeature` — Function that returns the specified replace face feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(sourceFaces: ObjectCollection, isTangentChain: bool, targetFaces: Base) -> ReplaceFaceFeatureInput` — Creates a ReplaceFaceFeatureInput object.
    - `sourceFaces`: Input the entities that define the source faces (the faces to be replaced).
    - `isTangentChain`: A boolean value for setting whether or not faces that are tangentially connected to the input faces (if any) will also be included.
    - `targetFaces`: Input the entities that define the target faces.
- `add(input: ReplaceFaceFeatureInput) -> ReplaceFaceFeature` — Creates a new replace face feature.
    - `input`: A ReplaceFaceFeatureInput object that defines the desired replace face.
- `itemByName(name: str) -> ReplaceFaceFeature` — Function that returns the specified replace face feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of replace face features in the collection.

### RevolveFeatureInput
This class defines the methods and properties that pertain to the definition of a revolve feature.
- `setAngleExtent(isSymmetric: bool, angle: ValueInput) -> bool` — Defines the extent of the revolution to be at a specified angle.
    - `isSymmetric`: Set to 'true' for a revolve symmetrical about the profile plane
    - `angle`: The ValueInput object that defines the angle of the revolution
- `setTwoSideAngleExtent(angleOne: ValueInput, angleTwo: ValueInput) -> bool` — Defines the angle of the revolve to be to applied to both sides of the profile at the specified angles.
    - `angleOne`: The ValueInput object that defines the angle for the first side of the revolution
    - `angleTwo`: The ValueInput object that defines the angle for the second side of the revolution
- `setOneSideToExtent(toEntity: Base, directionHint: Vector3D = None) -> bool` — Defines the extent of the revolve to be from the sketch or profile plane to the specified "To" face.
    - `toEntity`: The entity that defines the "to" extent.
    - `directionHint`: Specifies the direction of the revolve.
- `setTwoSideToExtent(toEntityOne: Base, toEntityTwo: Base) -> bool` — Defines the extents of the revolve to be from the sketch plane to specified faces in both directions.
    - `toEntityOne`: The first entity that defines the "to" extent.
    - `toEntityTwo`: The second entity that defines the "to" extent.
- prop `profile`: Base (rw) — Gets and sets the profiles or planar faces used to define the shape of the revolve.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the revolve.
- prop `axis`: Base (rw) — Gets and sets the entity used to define the axis of revolution.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the Revolve is created based on geometry (e.g.
- prop `isSolid`: bool (rw) — Specifies if the revolution should be created as a solid or surface.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `isProjectAxis`: bool (rw) — Specifies if the axis should be projected on the same plane as the profile sketch plane or not.

### RevolveFeatures
Collection that provides access to all of the existing revolve features in a design and supports the ability to create new revolve features.
- `item(index: int) -> RevolveFeature` — Function that returns the specified revolve feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(profile: Base, axis: Base, operation: FeatureOperations) -> RevolveFeatureInput` — Creates a new RevolveFeatureInput object that is used to specify the input needed to create a new revolve feature.
    - `profile`: The profile argument can be a single Profile, a single planar face, or an ObjectCollection consisting of multiple profiles and planar faces.
    - `axis`: The axis can be a sketch line, construction axis, linear edge or a face that defines an axis (cylinder, cone, torus, etc.).
    - `operation`: The operation type to perform.
- `add(input: RevolveFeatureInput) -> RevolveFeature` — Creates a new revolve feature based on the information provided by the provided RevolveFeatureInput object.
    - `input`: The RevolveFeatureInput object that specifies the input needed to create a new extrude
- `itemByName(name: str) -> RevolveFeature` — Function that returns the specified revolve feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of revolve features in the collection.

### RibFeatures
Collection that provides access to all of the existing rib features in a design.
- `item(index: int) -> RibFeature` — Function that returns the specified Rib feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> RibFeature` — Function that returns the specified Rib feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of Rib features in the collection.

### RuledSurfaceFeatureInput
This class defines the methods and properties that pertain to the definition of a Ruled Surface feature.
- prop `profile`: Base (rw) — Gets and sets the Profile object that defines the sketch geometry or edges that define the shape of the ruled surface.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the Ruled Surface is created based on geometry (e.g.
- prop `distance`: ValueInput (rw) — Gets and sets the ValueInput object that defines the Ruled Surface distance.
- prop `angle`: ValueInput (rw) — Gets and sets the ValueInput object that defines the Ruled Surface angle.
- prop `ruledSurfaceType`: RuledSurfaceTypes (rw) — Gets and sets the type of ruled surface to create.
- prop `direction`: Base (rw) — Gets and sets the entity that defines the direction when the ruled surface type is DirectionRuledSurfaceType.
- prop `alternateFace`: bool (rw) — Gets and sets if the other face is used for creation of the Ruled Surface.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the ruled surface.
- prop `cornerType`: RuledSurfaceCornerTypes (rw) — Gets and sets the corner type for the ruled surface, indicating if the corners will be rounded or mitered.

### RuledSurfaceFeatures
Collection that provides access to all of the existing Ruled Surface features in a component and supports the ability to create new Ruled Surface features.
- `item(index: int) -> RuledSurfaceFeature` — Function that returns the specified ruled surface feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(profile: Base, distance: ValueInput, angle: ValueInput, ruledSurfaceType: RuledSurfaceTypes, direction: Base = None) -> RuledSurfaceFeatureInput` — Creates a RuledSurfaceFeatureInput object that defines the input needed to create a ruled surface feature.
    - `profile`: A Profile object that defines the sketch geometry or edges that define the shape of the ruled surface.
    - `distance`: ValueInput object that defines the extension distance of the Ruled Surface..
    - `angle`: ValueInput object that defines angle to use when creating the Ruled Surface.
    - `ruledSurfaceType`: The Ruled Surface type (TangentRuledSurfaceType, NormalRuledSurfaceType, or DirectionRuledSurfaceType).
    - `direction`: If the ruled surface type is DirectionRuledSurfaceType, you must specify the direction.
- `add(input: RuledSurfaceFeatureInput) -> RuledSurfaceFeature` — Creates a new RuledSurface feature.
    - `input`: An RuledSurfaceFeatureInput object that defines the desired RuledSurface feature.
- `itemByName(name: str) -> RuledSurfaceFeature` — Function that returns the specified RuledSurface feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of RuledSurface features in the collection.

### ScaleFeatureInput
This class defines the methods and properties that pertain to the definition of a scale feature.
- `setToNonUniform(xScale: ValueInput, yScale: ValueInput, zScale: ValueInput) -> bool` — Sets the scale factor for the x, y, z directions to define a non-uniform scale.
    - `xScale`: A ValueInput object that defines the scale in the X direction.
    - `yScale`: A ValueInput object that defines the scale in the Y direction.
    - `zScale`: A ValueInput object that defines the scale in the Z direction.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the input entities.
- prop `point`: Base (rw) — Gets and sets the origin point of the scale.
- prop `scaleFactor`: ValueInput (rw) — Gets and sets the scale factor used for a uniform scale.
- prop `isUniform`: bool (ro) — Gets if the scale is uniform.
- prop `xScale`: ValueInput (ro) — Gets the scale in X direction.
- prop `yScale`: ValueInput (ro) — Gets the scale in Y direction.
- prop `zScale`: ValueInput (ro) — Gets the scale in Z direction.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### ScaleFeatures
Collection that provides access to all of the existing scale features in a component and supports the ability to create new scale features.
- `item(index: int) -> ScaleFeature` — Function that returns the specified scale feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputEntities: ObjectCollection, point: Base, scaleFactor: ValueInput) -> ScaleFeatureInput` — Creates a ScaleFeatureInput object.
    - `inputEntities`: This collection can contain sketches, BRep bodies and T-Spline bodies in parametric modeling.
    - `point`: Input a point as reference to scale.
    - `scaleFactor`: The ValueInput object that defines the scale factor for uniform scale.
- `add(input: ScaleFeatureInput) -> ScaleFeature` — Creates a new scale feature.
    - `input`: A ScaleFeatureInput object that defines the desired scale.
- `itemByName(name: str) -> ScaleFeature` — Function that returns the specified scale feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of scale features in the collection.

### SheetMetalChamferEdgeSet
** This class is a preview feature and may change in future releases.
- `deleteMe() -> bool` — Removes this edge set from its parent sheet metal chamfer feature.
- prop `edges`: list[BRepEdge] (rw) — Gets and sets the thickness-direction edges in this edge set.
- prop `distance`: ModelParameter (ro) — Returns the model parameter that controls the constant distance applied to every edge in this set.

### SheetMetalFilletEdgeSet
** This class is a preview feature and may change in future releases.
- `deleteMe() -> bool` — Removes this edge set from its parent sheet metal fillet feature.
- prop `edges`: list[BRepEdge] (rw) — Gets and sets the thickness-direction edges in this edge set.
- prop `radius`: ModelParameter (ro) — Returns the model parameter that controls the constant radius applied to every edge in this set.

### SheetMetalFilletEdgeSetInput
** This class is a preview feature and may change in future releases.
- prop `edges`: list[BRepEdge] (rw) — Gets and sets the thickness-direction edges in this edge set.
- prop `radius`: ValueInput (rw) — Gets and sets the constant radius applied to every edge in this set.

### SheetMetalFilletEdgeSetInputs
** This class is a preview feature and may change in future releases.
- `item(index: int) -> SheetMetalFilletEdgeSetInput` — Function that returns the specified edge-set input using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(edges: list[BRepEdge], radius: ValueInput) -> SheetMetalFilletEdgeSetInput` — Adds an edge set to the fillet input.
    - `edges`: The thickness-direction edges to fillet.
    - `radius`: The constant fillet radius applied to every edge in this set.
- prop `count`: int (ro) — The number of edge-set inputs in the collection.

### SheetMetalFilletEdgeSets
** This class is a preview feature and may change in future releases.
- `item(index: int) -> SheetMetalFilletEdgeSet` — Function that returns the specified edge set using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(edges: list[BRepEdge], radius: ValueInput) -> SheetMetalFilletEdgeSet` — Adds a new edge set to this fillet feature.
    - `edges`: The thickness-direction edges to fillet.
    - `radius`: The constant fillet radius applied to every edge in this set.
- prop `count`: int (ro) — The number of edge sets in the collection.

### ShellFeatureInput
This class defines the methods and properties that pertain to the definition of a shell feature.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the input faces/bodies.
- prop `isTangentChain`: bool (rw) — Gets and sets if any faces that are tangentially connected to any of the input faces will also be included in setting InputEntities.
- prop `insideThickness`: ValueInput (rw) — Gets and sets the inside thickness.
- prop `outsideThickness`: ValueInput (rw) — Gets and sets the outside thickness.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the shell is created based on geometry (e.g.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `shellType`: ShellTypes (rw) — The shell type used when creating a shell.

### ShellFeatures
Collection that provides access to all of the existing shell features in a component and supports the ability to create new shell features.
- `item(index: int) -> ShellFeature` — Function that returns the specified shell feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputEntities: ObjectCollection, isTangentChain: bool = True) -> ShellFeatureInput` — Creates a ShellFeatureInput object.
    - `inputEntities`: The collection contains the faces to remove and the bodies to perform shell.
    - `isTangentChain`: A boolean value for setting whether or not faces that are tangentially connected to the input faces (if any) will also be included.
- `add(input: ShellFeatureInput) -> ShellFeature` — Creates a new shell feature.
    - `input`: A ShellFeatureInput object that defines the desired shell.
- `itemByName(name: str) -> ShellFeature` — Function that returns the specified shell feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of shell features in the collection.

### SplitBodyFeatureInput
This class defines the methods and properties that pertain to the definition of a split body feature.
- prop `splitBodies`: Base (rw) — Gets and sets the input solid or open bodies to be split.
- prop `splittingTool`: Base (rw) — Gets and sets the entity that defines the splitting tool.
- prop `isSplittingToolExtended`: bool (rw) — Gets and sets whether or not the splitting tool is to be automatically extended (if possible) so as to completely intersect the bodyToSplit.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### SplitBodyFeatures
Collection that provides access to all of the existing split body features in a component and supports the ability to create new split body features.
- `item(index: int) -> SplitBodyFeature` — Function that returns the specified split body feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(splitBodies: Base, splittingTool: Base, isSplittingToolExtended: bool) -> SplitBodyFeatureInput` — Creates a SplitBodyFeatureInput object.
    - `splitBodies`: Input solid body or open bodies to be split.
    - `splittingTool`: Input entity that defines the splitting tool.
    - `isSplittingToolExtended`: A boolean value for setting whether or not the splitting tool is to be automatically extended (if possible) so as to completely intersect the bodyToSplit.
- `add(input: SplitBodyFeatureInput) -> SplitBodyFeature` — Creates a new split body feature.
    - `input`: A SplitBodyFeatureInput object that defines the desired split body feature.
- `itemByName(name: str) -> SplitBodyFeature` — Function that returns the specified split body feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of split body features in the collection.

### SplitFaceFeatureInput
This class defines the methods and properties that pertain to the definition of a split face feature.
- `setAlongVectorSplitType(directionEntity: Base) -> bool` — Sets the split type to project the splitting tool along the direction defined by the specified entity.
    - `directionEntity`: An entity that defines the direction of projection of the splitting tool.
- `setClosestPointSplitType() -> bool` — Sets the split type to be a curve that defined by projecting the splitting curve to the closest point on the surface.
- `setSurfaceIntersectionSplitType(isSplittingToolExtended: bool) -> bool` — Set the split type to be a surface to surface intersection.
    - `isSplittingToolExtended`: Specifies if the splitting tool should be extended so that is fully intersects the faces to be split.
- prop `facesToSplit`: ObjectCollection (rw) — Gets and sets the faces to be split.
- prop `splittingTool`: Base (rw) — Gets and sets the entity(s) that define the splitting tool(s).
- prop `isSplittingToolExtended`: bool (rw) — Gets and sets whether or not the splittingTool is to be automatically extended (if possible) so as to completely intersect the facesToSplit.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `splitType`: SplitFaceSplitTypes (ro) — Returns the type of split type currently defined.

### SplitFaceFeatures
Collection that provides access to all of the existing split face features in a component and supports the ability to create new split face features.
- `item(index: int) -> SplitFaceFeature` — Function that returns the specified split face feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(facesToSplit: ObjectCollection, splittingTool: Base, isSplittingToolExtended: bool) -> SplitFaceFeatureInput` — Creates a SplitFaceFeatureInput object.
    - `facesToSplit`: Input the faces to be split.
    - `splittingTool`: Input entity(s) that defines the splitting tool.
    - `isSplittingToolExtended`: A boolean value for setting whether or not the splittingTool is to be automatically extended (if possible) so as to completely intersect the faces that are to be split.
- `add(input: SplitFaceFeatureInput) -> SplitFaceFeature` — Creates a new split face feature.
    - `input`: A SplitFaceFeatureInput object that defines the desired split face feature.
- `itemByName(name: str) -> SplitFaceFeature` — Function that returns the specified split face feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of split face features in the collection.

### StitchFeatureInput
This class defines the methods and properties that pertain to the definition of a stitch feature.
- prop `stitchSurfaces`: ObjectCollection (rw) — Gets and sets the surfaces to stitch together.
- prop `tolerance`: ValueInput (rw) — Gets and sets the ValueInput object that defines the stitching tolerance.
- prop `operation`: FeatureOperations (rw) — Gets and sets the feature operation to perform.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### StitchFeatures
Collection that provides access to all of the existing Stitch features in a component and supports the ability to create new Stitch features.
- `item(index: int) -> StitchFeature` — Function that returns the specified stitch feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(stitchSurfaces: ObjectCollection, tolerance: ValueInput, operation: FeatureOperations = FeatureOperations.NewBodyFeatureOperation) -> StitchFeatureInput` — Creates a StitchFeatureInput object.
    - `stitchSurfaces`: The surfaces (open BRepBodies) to stitch together.
    - `tolerance`: ValueInput object that defines the stitching tolerance.
    - `operation`: Specifies the operation type for the result when the final result is a closed solid.
- `add(input: StitchFeatureInput) -> StitchFeature` — Creates a new stitch feature.
    - `input`: A StitchFeatureInput object that defines the desired stitch feature.
- `itemByName(name: str) -> StitchFeature` — Function that returns the specified stitch feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of Stitch features in the collection.

### SweepFeatureInput
This class defines the methods and properties that pertain to the definition of a sweep feature.
- prop `profile`: Base (rw) — Gets and sets the profiles or planar faces used to define the shape of the sweep.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the sweep.
- prop `path`: Path (rw) — Gets and sets the path to create the sweep.
- prop `distanceOne`: ValueInput (rw) — Gets and sets the distance for the first side.
- prop `distanceTwo`: ValueInput (rw) — Gets and sets the distance for the second side.
- prop `orientation`: SweepOrientationTypes (rw) — Gets and sets the sweep orientation.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the sweep is created based on geometry (e.g.
- prop `isSolid`: bool (rw) — Specifies if the sweep should be created as a solid or surface.
- prop `guideRail`: Path (rw) — Gets and sets the guide rail to create the sweep.
- prop `isDirectionFlipped`: bool (rw) — Gets and sets if the direction of the sweep is flipped.
- prop `profileScaling`: SweepProfileScalingOptions (rw) — Gets and sets the sweep profile scaling option.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `taperAngle`: ValueInput (rw) — Gets and sets the taper angle of the sweep.
- prop `twistAngle`: ValueInput (rw) — Gets and sets the twist angle of the sweep.
- prop `extent`: SweepExtentTypes (rw) — Gets and sets the sweep extent type.
- prop `guideSurfaces`: list[BRepFace] (rw) — Gets and sets the guide surfaces to create the sweep.
- prop `isChainSelection`: bool (rw) — Get and sets whether faces that are tangentially connected to the guide surfaces are also made guide surfaces.
- prop `solidBody`: BRepBody (rw) — Gets and sets the BRepBody object to sweep.
- prop `solidOrientation`: SweepSolidOrientationTypes (rw) — Gets and sets the solid sweep orientation.
- prop `solidAlignedAxis`: Base (rw) — Gets and sets the axis to align the solid being swept with.
- prop `solidTwistAxis`: Base (rw) — Gets and sets the twist axis of the solid being swept.

### SweepFeatures
Collection that provides access to all of the existing sweep features in a component and supports the ability to create new sweep features.
- `item(index: int) -> SweepFeature` — Function that returns the specified sweep feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(profile: Base, path: Path, operation: FeatureOperations) -> SweepFeatureInput` — Creates a SweepFeatureInput object for defining a simple sweep feature with only a path and no guide rail or surface.
    - `profile`: The profile argument can be a single Profile, a single planar face, or an ObjectCollection consisting of multiple profiles and planar faces.
    - `path`: The path to create the sweep.
    - `operation`: The feature operation to perform
- `add(input: SweepFeatureInput) -> SweepFeature` — Creates a new sweep feature.
    - `input`: A SweepFeatureInput object that defines the desired sweep.
- `itemByName(name: str) -> SweepFeature` — Function that returns the specified sweep feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- `createInputForSolid(solidBody: BRepBody, path: Path, operation: FeatureOperations) -> SweepFeatureInput` — Creates a SweepFeatureInput object for defining a simple sweep feature from a B-Rep solid with a path.
    - `solidBody`: The BRepBody object to sweep.
    - `path`: The Path object that defines the path the body will be swept along.
    - `operation`: The type of feature operation to perform.
- prop `count`: int (ro) — The number of sweep features in the collection.

### ThickenFeatureInput
This class defines the methods and properties that pertain to the definition of a Thicken feature.
- prop `inputFaces`: ObjectCollection (rw) — An ObjectCollection containing the face and/or patch bodies to thicken.
- prop `thickness`: ValueInput (rw) — Gets and sets the ValueInput object that defines the thickness distance.
- prop `isSymmetric`: bool (rw) — Gets and sets whether to add thickness symmetrically or only on one side of the face/s to thicken
- prop `operation`: FeatureOperations (rw) — Gets and sets the feature operation to perform.
- prop `isChainSelection`: bool (rw) — Get and sets whether faces that are tangentially connected to the input faces will be included in the thicken feature.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.
- prop `creationOccurrence`: Occurrence (rw) — In order for geometry to be transformed correctly, an Occurrence for creation needs to be specified when the Thicken feature is created based on geometry (e.g.
- prop `thickenType`: ThickenTypes (rw) — The thicken type used when creating a thicken.

### ThickenFeatures
Collection that provides access to all of the existing Thicken features in a component and supports the ability to create new Thicken features.
- `item(index: int) -> ThickenFeature` — Function that returns the specified Thicken feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputFaces: ObjectCollection, thickness: ValueInput, isSymmetric: bool, operation: FeatureOperations, isChainSelection: bool = True) -> ThickenFeatureInput` — Creates a ThickenFeatureInput object.
    - `inputFaces`: The faces or patch bodies to thicken.
    - `thickness`: ValueInput object that defines the thickness.
    - `isSymmetric`: A boolean value for setting whether to add thickness symmetrically or only on one side of the face/s to thicken
    - `operation`: The feature operation to perform.
    - `isChainSelection`: A boolean value for setting whether or not faces that are tangentially connected to the input faces (if any) will be included in the thicken.
- `add(input: ThickenFeatureInput) -> ThickenFeature` — Creates a new Thicken feature.
    - `input`: A FeatureInput object that defines the desired Thicken feature.
- `itemByName(name: str) -> ThickenFeature` — Function that returns the specified thicken feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of Thicken features in the collection.

### ThreadDataQuery
This object provides methods to query the thread data contained in the XML files in ThreadData folder within the Fusion install folder.
- `create(isTapered: bool = False) -> ThreadDataQuery` — Static method to create a new ThreadDataQuery object.
    - `isTapered`: Specifies if you want to query for standard or tapered holes.
- `allSizes(threadType: str) -> list[str]` — Returns an array/list of all the available thread sizes for a given thread type.
    - `threadType`: Specify the thread type.
- `allDesignations(threadType: str, size: str) -> list[str]` — returns an array/list of all the available thread designations for a thread type of a given size.
    - `threadType`: The thread type of the designation you want.
    - `size`: The thread size of the designation you want.
- `allClasses(isInternal: bool, threadType: str, designation: str) -> list[str]` — Returns and array/list of all the available classes for a thread type of a given thread designation.
    - `isInternal`: Indicates if the thread is an internal or external thread.
    - `threadType`: The thread type of the thread class you want.
    - `designation`: The thread designation of the thread class you want.
- `threadTypeCustomName(threadType: str) -> str` — Method that returns the custom name for a given thread type.
    - `threadType`: The thread type you want to get the custom name for.
- `threadTypeUnit(threadType: str) -> str` — Method that returns the unit for a given thread type.
    - `threadType`: The thread type you want to get the thread unit type for.
- `recommendThreadData(modelDiameter: float, isInternal: bool, threadType: str) -> tuple[bool, str, str]` — Method that gets the recommended thread data for a given cylinder diameter.
    - `modelDiameter`: The diameter of the cylinder the thread will be placed on.
    - `isInternal`: Indicates if the thread is an internal or external thread.
    - `threadType`: Specifies the thread type to query the thread data.
    - `designation`: The output thread designation.
    - `threadClass`: The output thread class.
- `getHubLibraryDisplayName(hubLibraryId: str) -> str` — Returns the display name for a given hub library.
    - `hubLibraryId`: The hub library ID, as returned by availableHubLibraryIds.
- `getHubLibraryThreadTypes(hubLibraryId: str) -> list[str]` — Returns thread types filtered by hub library.
    - `hubLibraryId`: The hub library ID to filter by, or an empty string for all sources.
- prop `allThreadTypes`: list[str] (ro) — This method returns an array of all the available thread types (families).
- prop `defaultInchThreadType`: str (ro) — Gets the default thread type for inch threads.
- prop `defaultMetricThreadType`: str (ro) — Gets the default thread type for metric threads.
- prop `isTapered`: bool (ro) — Returns if this ThreadDataQuery was created to query for standard or tapered threads.
- prop `publicThreadTypes`: list[str] (ro) — Returns thread types from the built-in public library only, excluding any hub library threads.
- prop `availableHubLibraryIds`: list[str] (ro) — Returns an array of available hub library IDs.

### ThreadFeatureInput
This class defines the methods and properties that pertain to the definition of a thread feature.
- prop `inputCylindricalFace`: BRepFace (rw) — Gets and sets the threaded face.
- prop `isModeled`: bool (rw) — Gets and sets if the thread is physical or cosmetic thread.
- prop `isFullLength`: bool (rw) — Gets and sets if this thread is the full length of the cylinder.
- prop `threadLength`: ValueInput (rw) — Gets and sets the thread length.
- prop `threadOffset`: ValueInput (rw) — Gets and sets the thread offset.
- prop `threadLocation`: ThreadLocations (rw) — Gets and sets which end of the cylinder the thread is measured from when it's not full length.
- prop `threadInfo`: ThreadInfo (rw) — Gets and sets the information that defines the thread.
- prop `inputCylindricalFaces`: ObjectCollection (rw) — Gets and sets the cylindrical input faces.
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### ThreadFeatures
Collection that provides access to all of the existing thread features in a component and supports the ability to create new thread features.
- `item(index: int) -> ThreadFeature` — Function that returns the specified thread feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(inputCylindricalFaces: Base, threadInfo: ThreadInfo) -> ThreadFeatureInput` — Creates a ThreadFeatureInput object.
    - `inputCylindricalFaces`: A single cylindrical BRep face or a collection of cylindrical BRep faces to thread.
    - `threadInfo`: The ThreadInfo object that defines the type and size of the thread to create.
- `add(input: ThreadFeatureInput) -> ThreadFeature` — Creates a new thread feature.
    - `input`: A ThreadFeatureInput object that defines the desired thread.
- `itemByName(name: str) -> ThreadFeature` — Function that returns the specified thread feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of thread features in the collection.

### ThreadInfo
This class defines the methods and properties that define the type and size of a thread.
- `create(isTapered: bool, isInternal: bool, threadType: str, threadDesignation: str, threadClass: str, isRightHanded: bool) -> ThreadInfo` — This method creates a new ThreadInfo object that can be used to create a thread or tapped-hole feature.
    - `isTapered`: Input Boolean that indicates if the thread is straight or tapered.
    - `isInternal`: Input Boolean that indicates if the thread is internal or external.
    - `threadType`: Input string that defines the thread type.
    - `threadDesignation`: Input string that contains the thread designation.
    - `threadClass`: Input string that defines the thread class.
    - `isRightHanded`: Input boolean that defines if the thread is right or left-handed.
- `redefine(isTapered: bool, isInternal: bool, threadType: str, threadDesignation: str, threadClass: str, isRightHanded: bool) -> bool` — Method that redefines an existing ThreadInfo object.
    - `isTapered`: Input Boolean that indicates if the thread is straight or tapered.
    - `isInternal`: Input Boolean that indicates if the thread is internal or external.
    - `threadType`: Input string that defines the thread type.
    - `threadDesignation`: Input string that defines the thread designation.
    - `threadClass`: Input string that defines the thread class.
    - `isRightHanded`: Input Boolean that specifies if the thread is straight or tapered.
- prop `threadType`: str (rw) — Returns and sets the string that defines the thread type.
- prop `threadSize`: str (ro) — Returns the string that defines the thread size.
- prop `threadDesignation`: str (rw) — Returns and sets the string that defines the thread designation.
- prop `threadClass`: str (rw) — Returns and sets the string that defines the thread class.
- prop `isInternal`: bool (rw) — Returns and sets if the thread is an internal or external thread.
- prop `threadAngle`: float (ro) — Returns the value that defines the thread angle.
- prop `threadPitch`: float (ro) — Returns the value that defines the thread pitch.
- prop `majorDiameter`: float (ro) — Returns the value that defines the major diameter.
- prop `minorDiameter`: float (ro) — Returns the value that defines the minor diameter.
- prop `pitchDiameter`: float (ro) — Returns the value that defines the pitch diameter.
- prop `isRightHanded`: bool (rw) — Gets and sets if the thread is right or left-handed thread.
- prop `isTapered`: bool (ro) — Indicates if this ThreadInfo object defines a standard or tapered thread.
- prop `taperAngle`: float (ro) — Returns the angle of the tapered thread in centimeters.
- prop `taperTapDrillDiameter`: float (ro) — Returns the Diameter of the tap drill required to create this tap.
- prop `taperUsefulThreadLength`: float (ro) — Returns the useful length of threads for a tapered thread in centimeters.
- prop `taperWrenchMakeupInternalDiameter`: float (ro) — The wrench makeup internal diameter for a taper pipe thread, also known as the effective thread diameter, is the diameter at the point where the thread engagement occurs when the pipe is tightened with a …
- prop `taperThreadHeight`: float (ro) — Returns the height of a tapered thread in centimeters.
- prop `isHubLibraryThread`: bool (ro) — Returns true if this thread is from a hub library, false for built-in public threads.
- prop `hubLibraryId`: str (ro) — Returns the hub library ID for hub library threads, or an empty string for public threads.

### Timeline
A collection of TimelineObjects in a parametric design.
- `moveToBeginning() -> bool` — Moves the marker to the beginning of the timeline.
- `moveToEnd() -> bool` — Moves the marker to the end of the timeline.
- `movetoNextStep() -> bool` — Moves the marker to the next step in the timeline.
- `moveToPreviousStep() -> bool` — Moves the marker to the previous step in the timeline.
- `play() -> bool` — Plays the timeline beginning at the current position of the marker.
- `item(index: int) -> TimelineObject` — Function that returns the specified item in the timeline using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `deleteAllAfterMarker() -> bool` — Deletes all objects in the timeline that are after the current position of the marker.
- prop `markerPosition`: int (rw) — Gets and sets the current position of the marker where 0 is at the beginning of the timeline and the value of Timeline.count is the end of the timeline.
- prop `count`: int (ro) — Returns the number of items in the collection.
- prop `timelineGroups`: TimelineGroups (ro) — Returns the collection of groups within the timeline.
- prop `parentDesign`: Design (ro) — Returns the parametric Design that owns this Timeline.

### TimelineGroups
Provides access to the time line groups within a design and provides methods to create new groups.
- `add(startIndex: int, endIndex: int) -> TimelineGroup` — Creates a new group within the timeline.
    - `startIndex`: The index of the first item in the timeline that will be added to the group.
    - `endIndex`: The index of the last item in the timeline that will be added to the group.
- `item(index: int) -> TimelineGroup` — Function that returns the specified timeline group using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> list[TimelineGroup]` — Returns the timeline groups with the specified name.
    - `name`: The name of the timeline group as displayed in the timeline.
- prop `count`: int (ro) — Returns the number of items in the collection.

### TimelineObject
Represents an object in the timeline.
- `rollTo(rollBefore: bool) -> bool` — Rolls the timeline by repositioning the marker to either before or after this object.
    - `rollBefore`: Set rollBefore to true to reposition the marker before this object or to false to reposition the marker after this object
- `canReorder(beforeIndex: int = -1) -> bool` — Checks to see if this object can be reordered to the specified position.
    - `beforeIndex`: The index number of the position in the timeline to check
- `reorder(beforeIndex: int = -1) -> bool` — Reorders this object to the position specified.
    - `beforeIndex`: The index number of the position in the timeline to place this object before
- `deleteObject() -> bool` — Deletes this TimelineObject and its associated feature from the design.
- prop `isSuppressed`: bool (rw) — Gets and sets if this object is suppressed.
- prop `parentGroup`: TimelineGroup (ro) — Returns the parent group, if this object is part of a group.
- prop `index`: int (ro) — Returns the position of this item within the timeline where the first item has an index of 0.
- prop `isRolledBack`: bool (ro) — Indicates if this item is currently not being computed because it has been rolled back.
- prop `entity`: Base (ro) — Returns the entity associated with this timeline object.
- prop `isGroup`: bool (ro) — Indicates if this TimelineObject represents a group.
- prop `name`: str (rw) — Gets and sets the name of this timeline object.
- prop `healthState`: FeatureHealthStates (ro) — Returns the current health state of the object associated with this TimelineObject.
- prop `errorOrWarningMessage`: str (ro) — Returns the error or warning message in the case where the healthState property returns either WarningFeatureHealthState or ErrorFeatureHealthState.
- prop `parentTimeline`: Timeline (ro) — Returns the Timeline that owns this TimelineObject.
- prop `isDeletable`: bool (ro) — Indicates whether this TimelineObject can be deleted standalone using deleteObject().

### TrimFeatureInput
This class defines the methods and properties that pertain to the definition of a TrimFeatureInput.
- `cancel() -> bool` — To determine the possible boundaries and allow you to choose which cells to keep, the trim feature does a partial compute when the input object is created.
- prop `bRepCells`: BRepCells (ro) — Returns the collection of the valid cells that have been calculated based on the trim tool.
- prop `trimTool`: Base (rw) — Gets and sets the entity (a patch body, B-Rep face, construction plane or sketch curve) that intersects the trim tool
- prop `targetBaseFeature`: BaseFeature (rw) — When creating a feature that is owned by a base feature, set this property to the base feature you want to associate the new feature with.

### TrimFeatures
Collection that provides access to all of the existing trim features in a component and supports the ability to create new trim features.
- `item(index: int) -> TrimFeature` — Function that returns the specified trim feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(trimTool: Base) -> TrimFeatureInput` — Creates a TrimFeatureInput object.
    - `trimTool`: A patch body, B-Rep face, construction plane or sketch curve that intersects the surface or surfaces to be trimmed
- `add(input: TrimFeatureInput) -> TrimFeature` — Creates a new trim feature.
    - `input`: A TrimFeatureInput object that defines the desired trim feature.
- `itemByName(name: str) -> TrimFeature` — Function that returns the specified trim feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of trim features in the collection.

### UserParameters
Provides access to the User Parameters within a design and provides methods to create new user parameters.
- `item(index: int) -> UserParameter` — Function that returns the specified User Parameter using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> UserParameter` — Function that returns the specified User Parameter using the name of the parameter as it is displayed in the parameters dialog.
    - `name`: The name of the User Parameter as it is displayed in the parameters dialog
- `add(name: str, value: ValueInput, units: str, comment: str) -> UserParameter` — Adds a new user parameter to the collection.
    - `name`: The name of the parameter.
    - `value`: ValueInput object that specifies the value of the parameter.
    - `units`: The units to use for the value of the parameter.
    - `comment`: The comment to display in the parameters dialog.
- `asArray() -> list[UserParameter]` — Returns the user parameters in the design as an array.
- `exportUserParameters(userParameterArray: list[UserParameter], filename: str) -> bool` — Function that exports a list of user parameters to a csv file.
    - `userParameterArray`: The array of user parameters to export.
    - `filename`: The full filename (path and file) of the file to write the parameters to.
- `importUserParameters(filename: str) -> bool` — Function that imports a list of user parameters from a csv file.
    - `filename`: The full filename (path and file) of the file to read the parameters from.
- prop `count`: int (ro) — Returns the number of parameters in the collection.
- prop `design`: Design (ro) — Returns the design that owns the user parameters collection.

### WebFeatures
Collection that provides access to all of the existing web features in a design.
- `item(index: int) -> WebFeature` — Function that returns the specified web feature using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> WebFeature` — Function that returns the specified web feature using the name of the feature.
    - `name`: The name of the feature within the collection to return.
- prop `count`: int (ro) — The number of web features in the collection.

### AllExtentDefinition (ExtentDefinition)
Defines the inputs for an AllExtentDefinition object.
- prop `direction`: ExtentDirections (rw) — Gets and sets the direction of the extent.

### AngleExtentDefinition (ExtentDefinition)
Defines the inputs for an AngleExtentDefinition object.
- prop `isSymmetric`: bool (rw) — Gets and sets if the angle extent is in one direction or symmetric.
- prop `angle`: ModelParameter (ro) — Gets the ModelParameter that defines the angle.

### AsymmetricFilletEdgeSet (FilletEdgeSet)
Provides access to the edges and the parameters associated with an asymmetric fillet.
- prop `edges`: ObjectCollection (rw) — Gets and sets an ObjectCollection containing the BRepEdge, BRepFace, and Feature that are filleted.
- prop `offsetOne`: ModelParameter (ro) — Returns the model parameter that controls the offset distance of the fillet in the first direction You can edit the offset by using the properties on the returned ModelParameter object.
- prop `offsetTwo`: ModelParameter (ro) — Returns the model parameter that controls the offset distance of the fillet in the second direction You can edit the offset by using the properties on the returned ModelParameter object.
- prop `isFlipped`: bool (rw) — Gets and sets if offsets are reversed.

### AsymmetricFilletEdgeSetInput (FilletEdgeSetInput)
Provides access to the edges and the parameters associated with an asymmetric fillet.
- prop `offsetOne`: ValueInput (rw) — Gets and sets a ValueInput object that defines the first offset of the asymmetric fillet.
- prop `offsetTwo`: ValueInput (rw) — Gets and sets a ValueInput object that defines the second offset value of the asymmetric fillet.
- prop `isFlipped`: bool (rw) — Gets and sets if offsets are reversed.

### BoundaryFillFeature (Feature)
Object that represents an existing boundary fill feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> BoundaryFillFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `applyCellChanges() -> bool` — After making any changes to the set of selected cells you must call this method to indicate all changes have been made and to apply those changes to the feature.
- prop `tools`: ObjectCollection (rw) — A collection of construction planes and open or closed BRepBody objects that define the set of boundaries that have been used in the calculation of available closed boundaries.
- prop `bRepCells`: BRepCells (ro) — Gets the set of closed boundaries that have been calculated based on the current set of tools.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the boundary fill feature.
- prop `nativeObject`: BoundaryFillFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `isRemoveTools`: bool (rw) — Gets and sets whether any BRepBodys that were used as tools should be removed as part of the feature creation.

### ChamferFeature (Feature)
Object that represents an existing chamfer feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> ChamferFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `nativeObject`: ChamferFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `cornerType`: ChamferCornerTypes (rw) — Gets and sets the type of corner to be modeled when multiple edges connect at a vertex.
- prop `edgeSets`: ChamferEdgeSets (ro) — Returns the edge sets associated with this chamfer.

### ChordLengthFilletEdgeSet (FilletEdgeSet)
Provides access to the edges and the parameter associated with a chord length fillet.
- prop `edges`: ObjectCollection (rw) — Gets and sets an ObjectCollection containing the BRepEdge, BRepFace, and Feature that are filleted.
- prop `chordLength`: ModelParameter (ro) — Returns the model parameter that controls the chord length of the fillet.

### ChordLengthFilletEdgeSetInput (FilletEdgeSetInput)
Provides access to the edges and the parameter associated with a chord length fillet.
- prop `chordLength`: ValueInput (rw) — Gets and sets a ValueInput object that defines the chord length of the fillet.

### CircularPatternConstraint (GeometricConstraint)
A circular pattern constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> CircularPatternConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entities`: list[SketchEntity] (rw) — Gets and sets the entities to pattern.
- prop `createdEntities`: list[SketchEntity] (ro) — Returns an array that contains all of the sketch entities that were created as a result of the pattern.
- prop `centerPoint`: SketchPoint (rw) — Gets and sets the sketch point that defines the center of the pattern.
- prop `quantity`: ModelParameter (ro) — Returns the parameter that controls the number of instances in the pattern.
- prop `totalAngle`: ModelParameter (ro) — Returns the parameter that controls the number of instances in the pattern.
- prop `isSymmetric`: bool (rw) — Gets and sets if the angle extent is in one direction or is symmetric.
- prop `isSuppressed`: list[bool] (rw) — Specifies which, if any, instances of the pattern are suppressed.
- prop `nativeObject`: CircularPatternConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### CircularPatternFeature (Feature)
Object that represents an existing circular pattern feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> CircularPatternFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the entities to pattern using an ObjectCollection.
- prop `axis`: Base (rw) — Gets and sets the axis of circular pattern.
- prop `totalAngle`: ModelParameter (ro) — Returns the parameter controlling the total angle.
- prop `isSymmetric`: bool (rw) — Gets and sets if the angle extent is in one direction or symmetric.
- prop `quantity`: ModelParameter (ro) — Returns the parameter controlling the number of pattern elements, including any suppressed elements.
- prop `suppressedElementsIds`: list[int] (rw) — Gets and sets the id's of the elements to suppress.
- prop `patternElements`: PatternElements (ro) — Gets the PatternElements collection that contains the elements created by this pattern.
- prop `resultFeatures`: ObjectCollection (ro) — Returns the features that were created as a result of this pattern.
- prop `nativeObject`: CircularPatternFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `patternEntityType`: PatternEntityTypes (ro) — Returns the type of entities the pattern consists of.
- prop `patternComputeOption`: PatternComputeOptions (rw) — Gets and sets the compute option for this pattern feature.

### CoilFeature (Feature)
Object that represents an existing coil primitive feature in a design.

### CombineFeature (Feature)
Object that represents an existing Combine feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> CombineFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `targetBody`: BRepBody (rw) — Gets and sets the BRep Body object that represents the blank body.
- prop `toolBodies`: ObjectCollection (rw) — Gets and sets the BRep Body objects that represent the tool bodies.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the combine.
- prop `isNewComponent`: bool (ro) — Gets a boolean value for whether or not a new component was created when this feature was created.
- prop `isKeepToolBodies`: bool (rw) — Gets and sets a boolean value for whether or not the tool bodies are retrained after the combine results.
- prop `nativeObject`: CombineFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### ConstantRadiusFilletEdgeSet (FilletEdgeSet)
Provides access to the edges and the parameter associated with a constant radius fillet.
- prop `edges`: ObjectCollection (rw) — Gets and sets an ObjectCollection containing the BRepEdge, BRepFace, and Feature that are filleted.
- prop `radius`: ModelParameter (ro) — Returns the model parameter that controls the radius of the fillet.

### ConstantRadiusFilletEdgeSetInput (FilletEdgeSetInput)
Provides access to the edges and the parameter associated with a constant radius fillet.
- prop `radius`: ValueInput (rw) — Gets and sets ValueInput object that defines the radius of the fillet.

### ConstructionAxisByLineDefinition (ConstructionAxisDefinition)
The definition for a non-parametric construction axis.
- prop `axis`: InfiniteLine3D (rw) — Gets and sets the infinite line that defines the position and direction of the axis

### ConstructionAxisCircularFaceDefinition (ConstructionAxisDefinition)
The definition for a parametric construction axis created using the SetbyCircularFace method
- prop `circularFace`: BRepFace (rw) — Gets and sets the cylinder, cone, or torus this work axis is parametrically dependent on.

### ConstructionAxisEdgeDefinition (ConstructionAxisDefinition)
The definition for a parametric construction axis created using the SetbyEdge method
- prop `edgeEntity`: Base (rw) — Gets and sets the linear edge, construction line, or sketch line that defines the construction axis.

### ConstructionAxisNormalToFaceAtPointDefinition (ConstructionAxisDefinition)
The definition for a parametric construction axis created using the SetByNormalToFaceAtPoint method
- `redefine(face: Base, pointEntity: Base) -> bool` — Redefines the input geometry of the construction axis.
    - `face`: The face the axis is normal to
    - `pointEntity`: The point that positions the axis
- `redefineWithSnapPoint(face: BRepFace, snapPoint: ConstructionSnapPoint) -> bool` — Redefines the input geometry of the construction axis using a ConstructionSnapPoint to position the axis on a face.
    - `face`: The face the axis is normal to.
    - `snapPoint`: The ConstructionSnapPoint describing the location the axis passes through.
- prop `face`: Base (ro) — Gets the face the axis is normal to
- prop `pointEntity`: Base (ro) — Gets the point that positions the axis

### ConstructionAxisPerpendicularAtPointDefinition (ConstructionAxisDefinition)
The definition for a parametric construction axis created using the SetByPerpendicularAtPoint method
- `redefine(face: BRepFace, pointEntity: Base) -> bool` — Redefines the input geometry of the construction axis.
    - `face`: The face (BRepFace object) to create the axis perpendicular to.
    - `pointEntity`: The point (sketch point, vertex, construction point) used to position the axis.
- prop `face`: BRepFace (ro) — Returns the face the construction axis is perpendicular to.
- prop `point`: Base (ro) — Returns the point (construction or sketch point) that positions the axis.

### ConstructionAxisTwoPlaneDefinition (ConstructionAxisDefinition)
The definition for a parametric construction axis created using the SetByTwoPlanes method
- `redefine(planarEntityOne: Base, planarEntityTwo: Base) -> bool` — Redefines the input geometry of the construction axis.
    - `planarEntityOne`: The first planar face or construction plane
    - `planarEntityTwo`: The second planar face or construction plane
- prop `planarEntityOne`: Base (ro) — Gets the first planar face or construction plane
- prop `planarEntityTwo`: Base (ro) — Gets the second planar face or construction plane

### ConstructionAxisTwoPointDefinition (ConstructionAxisDefinition)
The definition for a parametric construction axis created using the SetbyTwoPoints method
- `redefine(pointEntityOne: Base, pointEntityTwo: Base) -> bool` — Redefines the input geometry of the construction axis.
    - `pointEntityOne`: The first point
    - `pointEntityTwo`: The second point
- `redefineByTwoSnapPoints(snapPointOne: ConstructionSnapPoint, snapPointTwo: ConstructionSnapPoint) -> bool` — Redefines the input geometry of the construction axis using two snap points.
    - `snapPointOne`: The first ConstructionSnapPoint the axis passes through.
    - `snapPointTwo`: The second ConstructionSnapPoint the axis passes through.
- prop `pointEntityOne`: Base (ro) — Gets the first point.
- prop `pointEntityTwo`: Base (ro) — Gets the second point.

### ConstructionPlaneAtAngleDefinition (ConstructionPlaneDefinition)
ConstructionPlaneAtAngleDefinition defines a ConstructionPlane by an angle around a linear entity.
- `redefine(angle: ValueInput, linearEntity: Base, planarEntity: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `angle`: A ValueInput object that defines the angle at which to create the construction plane
    - `linearEntity`: The linear edge, construction line, or sketch line that defines the axis of rotation to measure the angle about
    - `planarEntity`: A plane, planar face or construction plane the angle of the construction plane is measured from
- prop `angle`: Parameter (ro) — Returns a Parameter object that controls the value of the angle.
- prop `linearEntity`: Base (ro) — Gets the linear edge, construction line, or sketch line that defines the axis of rotation for the construction plane.
- prop `planarEntity`: Base (ro) — Gets the planar face or construction plane the angle for this construction plane is measured from and is parametrically dependent on.

### ConstructionPlaneAtAngleOnCurvedFaceDefinition (ConstructionPlaneDefinition)
ConstructionPlaneAtAngleOnCurvedFaceDefinition defines a ConstructionPlane by an angle around the axis inferred from a curved face.
- `redefine(angle: ValueInput, curvedFace: Base, planarEntity: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `angle`: A ValueInput object that defines the angle at which to create the construction plane.
    - `curvedFace`: The cylindrical or conical curved face that defines the axis of rotation.
    - `planarEntity`: A plane, planar face or construction plane the angle of the construction plane is measured from.
- prop `angle`: Parameter (ro) — Returns a Parameter object that controls the value of the angle.
- prop `curvedFace`: Base (ro) — Gets the cylindrical or conical curved face that defines the axis of rotation for the construction plane.
- prop `planarEntity`: Base (ro) — Gets the planar face or construction plane the angle for this construction plane is measured from and is parametrically dependent on.

### ConstructionPlaneByPlaneDefinition (ConstructionPlaneDefinition)
The definition for a non-parametric construction plane.
- prop `plane`: Plane (rw) — Gets and sets the position of the construction plane.

### ConstructionPlaneMidplaneDefinition (ConstructionPlaneDefinition)
ConstructionPlaneMidplaneDefinition defines a ConstructionPlane by...
- `redefine(planarEntityOne: Base, planarEntityTwo: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `planarEntityOne`: The first planar face or construction plane that defines this ConstructionPlane.
    - `planarEntityTwo`: The second planar face or construction plane that defines this ConstructionPlane.
- prop `planarEntityOne`: Base (ro) — Gets the first planar face or construction plane that defines this ConstructionPlane.
- prop `planarEntityTwo`: Base (ro) — Gets the second planar face or construction plane that defines this ConstructionPlane.

### ConstructionPlaneOffsetDefinition (ConstructionPlaneDefinition)
ConstructionPlaneOffsetDefinition defines a construction plane that is offset by a specified distance from a planar face or construction plane by a specified distance.
- `redefine(offset: ValueInput, planarEntity: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `offset`: ValueInput object that specifies the offset distance
    - `planarEntity`: A plane, planar face or construction plane from which to measure the offset from
- prop `offset`: Parameter (ro) — Returns a Parameter object that controls the value of the offset.
- prop `planarEntity`: Base (ro) — Gets the planar face or construction plane this construction plane is parametrically dependent on.

### ConstructionPlaneOffsetThroughPointDefinition (ConstructionPlaneDefinition)
Defines a construction plane that is offset from a planar face or construction plane and whose offset distance is defined by a vertex, sketch point, or construction point where the plane passes through the point.
- `redefine(planarEntity: Base, point: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `planarEntity`: A planar BRepFace or ConstructionPlane that the new construction plane will be offset from.
    - `point`: A BRepVertex, SketchPoint, or ConstructionPoint that defines the offset distance.
- prop `point`: Base (ro) — Returns the point that controls the offset.
- prop `planarEntity`: Base (ro) — Returns the planar face or construction plane this construction plane is parametrically dependent on.

### ConstructionPlanePathDefinition (ConstructionPlaneDefinition)
The definition for a parametric construction plane created using the setByPath method.
- `redefine(path: Path, distanceType: PathDistanceTypes, distance: ValueInput) -> bool` — Redefines the input geometry of the construction plane using Proportional or Absolute (physical distance) positioning via setByPath.
    - `path`: Specifies the Path object the construction plane will be redefined on.
    - `distanceType`: Specifies PathDistanceTypes value indicating the measurement type for distance.
    - `distance`: Specifies the distance to determine the position on the specified path to place the construction plane.
- `redefineToObject(path: Path, toObject: Base, offset: ValueInput) -> bool` — Redefines the input geometry of the construction plane using To Object positioning via setByPathToObject.
    - `path`: Specifies the Path object the construction plane will be redefined on.
    - `toObject`: Specifies the point entity the construction plane is positioned to.
    - `offset`: Specifies the signed offset from the target along the path.
- prop `path`: Path (ro) — Returns the Path object the construction plane was created on.
- prop `distanceType`: PathDistanceTypes (ro) — Returns an PathDistanceTypes value indicating the measurement type for distance.
- prop `distance`: ModelParameter (ro) — Returns the ModelParameter that controls position along the path.
- prop `toObject`: Base (ro) — Returns the target ("to object") point entity, or null when the plane was not created using setByPathToObject (Proportional or Absolute planes).
- prop `offset`: ModelParameter (ro) — Returns the ModelParameter controlling the signed offset from the target along the path, or null when the plane was not created using setByPathToObject (Proportional or Absolute planes).

### ConstructionPlanePerpendicularDefinition (ConstructionPlaneDefinition)
ConstructionPlanePerpendicularDefinition defines a ConstructionPlane that is perpendicular to the input face or plane.
- `redefine(planarEntity: Base, distance: ValueInput = None, referenceEntity: Base = None, useUDirection: bool = True) -> bool` — Redefines the input geometry of the construction plane.
    - `planarEntity`: The face or plane the construction plane will be perpendicular to.
    - `distance`: An optional ValueInput specifying the offset distance.
    - `referenceEntity`: An optional reference entity that the new plane passes through.
    - `useUDirection`: True to align with the U axis of the reference face; false to align with the V axis.
- prop `planarEntity`: Base (ro) — Gets the face or plane the construction plane is perpendicular to.
- prop `referenceEntity`: Base (ro) — Gets the optional reference entity that the construction plane passes through.
- prop `distance`: ModelParameter (ro) — Returns the ModelParameter object that controls the offset distance of the construction plane from its base position.
- prop `isUDirection`: bool (ro) — Returns true if the construction plane is aligned with the U axis of the reference face; returns false if it is aligned with the V axis.

### ConstructionPlaneTangentAtPointDefinition (ConstructionPlaneDefinition)
ConstructionPlaneTangentAtPointDefinition defines a ConstructionPlane tangent to a face and aligned to a point.
- `redefine(tangentFace: Base, pointEntity: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `tangentFace`: The face to create the plane tangent to
    - `pointEntity`: The point (sketch point, vertex, construction point) used to align the plane.
- prop `tangentFace`: BRepFace (ro) — Gets the tangent face.
- prop `pointEntity`: Base (ro) — Gets the point (sketch point, vertex, construction point) used to align the plane.

### ConstructionPlaneTangentDefinition (ConstructionPlaneDefinition)
ConstructionPlaneTangentDefinition defines a ConstructionPlane tangent to a cylindrical or conical face at a point.
- `redefine(angle: ValueInput, tangentFace: Base, planarEntity: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `angle`: A Value object that defines the angle of the construction plane
    - `tangentFace`: The cylindrical or conical face that the construction plane is tangent to.
    - `planarEntity`: The planar face or construction plane the angle for this construction plane is measured from
- prop `angle`: Parameter (ro) — Returns a Value object that for a transient definition provides the current assigned value.
- prop `tangentFace`: Base (ro) — Gets the cylindrical or conical face that the construction plane is tangent to.
- prop `planarEntity`: Base (ro) — Gets the planar face or construction plane the angle for this construction plane is measured from and is parametrically dependent on.

### ConstructionPlaneThreePointsDefinition (ConstructionPlaneDefinition)
ConstructionPlaneThreePointDefinition defines a ConstructionPlane by 3 point entities (e.g.
- `redefine(pointEntityOne: Base, pointEntityTwo: Base, pointEntityThree: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `pointEntityOne`: Gets the first construction point, sketch point or vertex.
    - `pointEntityTwo`: Gets the second construction point, sketch point or vertex.
    - `pointEntityThree`: Gets the third construction point, sketch point or vertex.
- `redefineWithSnapPoints(snapPointOne: ConstructionSnapPoint, snapPointTwo: ConstructionSnapPoint, snapPointThree: ConstructionSnapPoint) -> bool` — Redefines the input geometry of the construction plane using three ConstructionSnapPoint objects.
    - `snapPointOne`: The first ConstructionSnapPoint the plane passes through.
    - `snapPointTwo`: The second ConstructionSnapPoint the plane passes through.
    - `snapPointThree`: The third ConstructionSnapPoint the plane passes through.
- prop `pointEntityOne`: Base (ro) — Gets the first construction point, sketch point or vertex.
- prop `pointEntityTwo`: Base (ro) — Gets the second construction point, sketch point or vertex.
- prop `pointEntityThree`: Base (ro) — Gets the third construction point, sketch point or vertex.

### ConstructionPlaneTwoEdgesDefinition (ConstructionPlaneDefinition)
ConstructionPlaneTwoEdgesDefinition defines a ConstructionPlane by two co-planar linear entities like edges, sketch lines or construction axis.
- `redefine(linearEntityOne: Base, linearEntityTwo: Base) -> bool` — Redefines the input geometry of the construction plane.
    - `linearEntityOne`: The first linear edge, construction line, or sketch line that defines the construction plane.
    - `linearEntityTwo`: The second linear edge, construction line, or sketch line that defines the construction plane.
- prop `linearEntityOne`: Base (ro) — Gets the first linear edge, construction line, or sketch line that defines the construction plane.
- prop `linearEntityTwo`: Base (ro) — Gets the second linear edge, construction line, or sketch line that defines the construction plane.

### ConstructionPointCenterDefinition (ConstructionPointDefinition)
The definition for a parametric construction point created using the SetbyCenter method
- prop `circularEntity`: Base (rw) — Gets and sets the spherical face (sphere or torus), circular edge or sketch arc/circle whose center defines the location for the construction point.

### ConstructionPointEdgePlaneDefinition (ConstructionPointDefinition)
The definition for a parametric construction point created using the SetbyEdgePlane method
- `redefine(edge: Base, plane: Base) -> bool` — Redefines the input geometry of the construction point.
    - `edge`: A linear B-Rep edge, construction axis or sketch line.
    - `plane`: A plane, planar B-Rep face or construction plane.
- prop `edge`: Base (ro) — A linear B-Rep edge, construction axis or sketch line.
- prop `plane`: Base (ro) — A plane, planar B-Rep face or construction plane.

### ConstructionPointPathDefinition (ConstructionPointDefinition)
The definition for a parametric construction point created using the setByPath method
- `redefine(path: Path, distanceType: PathDistanceTypes, distance: ValueInput) -> bool` — Redefines the input geometry of the construction point.
    - `path`: Specifies the Path object the construction point will be redefined on.
    - `distanceType`: Specifies PathDistanceTypes value indicating the measurement type for distance.
    - `distance`: Specifies the distance to determine the position on the specified path to place the construction point.
- prop `path`: Path (ro) — Returns Path object the construction point was created on.
- prop `distanceType`: PathDistanceTypes (ro) — Returns an PathDistanceTypes value indicating the measurement type for distance.
- prop `distance`: ModelParameter (ro) — Returns the parameter that controls the distance.

### ConstructionPointPointDefinition (ConstructionPointDefinition)
The definition for a parametric construction point created using the SetbyPoint method All non-parametric constructions points will return this type of definition regardless of the method used to initially create them.
- `redefineBySnapPoint(snapPoint: ConstructionSnapPoint) -> bool` — Redefines the input geometry of the construction point using a snap point.
    - `snapPoint`: The ConstructionSnapPoint defining the new location of the construction point.
- prop `pointEntity`: Base (rw) — Gets and sets the position of the point using a construction point, sketch point or vertex.

### ConstructionPointThreePlanesDefinition (ConstructionPointDefinition)
The definition for a parametric construction point created using the SetbyThreePlanes method
- `redefine(planeOne: Base, planeTwo: Base, planeThree: Base) -> bool` — Redefines the input geometry of the construction point.
    - `planeOne`: The first plane or planar face to intersect
    - `planeTwo`: The second plane or planar face to intersect
    - `planeThree`: The third plane or planar face to intersect
- prop `planeOne`: Base (ro) — The first plane or planar face
- prop `planeTwo`: Base (ro) — The second plane or planar face
- prop `planeThree`: Base (ro) — The third plane or planar face

### ConstructionPointTwoEdgesDefinition (ConstructionPointDefinition)
The definition for a parametric construction point created using the SetbyTwoEdges method
- `redefine(edgeOne: Base, edgeTwo: Base) -> bool` — Redefines the input geometry of the construction point.
    - `edgeOne`: The first B-Rep edge or sketch line.
    - `edgeTwo`: The second B-Rep edge or sketch line.
- prop `edgeOne`: Base (ro) — Returns a B-Rep edge or sketch line
- prop `edgeTwo`: Base (ro) — Returns a B-Rep edge or sketch line

### DeleteFaceFeature (Feature)
Object that represents an existing DeleteFaceFeature object in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> DeleteFaceFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `deletedFaces`: list[BRepFace] (rw) — Gets and sets the set of faces that are deleted by this feature.
- prop `nativeObject`: DeleteFaceFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### DistanceAndAngleChamferEdgeSet (ChamferEdgeSet)
Provides access to the edges and the parameter associated with a chord length fillet.
- prop `edges`: ObjectCollection (rw) — Gets and sets the edges that will be chamfered.
- prop `distance`: ModelParameter (ro) — Returns the model parameter that controls the offset distance of the chamfer.
- prop `angle`: ModelParameter (ro) — Returns the model parameter that controls the angle of the chamfer.
- prop `isFlipped`: bool (rw) — Gets and sets if the chamfer is flipped.

### DistanceExtentDefinition (ExtentDefinition)
Defines the inputs for a distance ExtentDefinition object.
- `create(distance: ValueInput) -> DistanceExtentDefinition` — Statically creates a new DistanceExtentDefinition object.
    - `distance`: A ValueInput that defines the distance of the extrusion.
- prop `distance`: ModelParameter (ro) — Returns the parameter controlling the distance.

### DraftAnalysis (Analysis)
Represents any existing Draft Analysis that exist in the design.

### DraftFeature (Feature)
Object that represents an existing draft feature in a design.
- `setSingleAngle(isSymmetric: bool, angle: ValueInput) -> bool` — Changes the definition of the feature so that a single angle is used for all drafts.
    - `isSymmetric`: Set to true if the faces are to be split along the plane or parting line and drafted symmetrically.
    - `angle`: The ValueInput object that defines the angle of the draft.
- `setTwoAngles(angleOne: ValueInput, angleTwo: ValueInput) -> bool` — Changes the definition of the feature so that the surfaces are split along the draft plane or parting line and the faces on each side of the plane are drafted independently.
    - `angleOne`: The ValueInput object that defines the angle for the faces on the first side of the draft plane or parting line.
    - `angleTwo`: The ValueInput object that defines the angle for the faces on the second side of the draft plane or parting line.
- `createForAssemblyContext(occurrence: Occurrence) -> DraftFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `setFixedPartingLineDraftFeatureType(partingLineCurves: list[Base], isChained: bool) -> bool` — ** This method is a preview feature and may change in future releases.
    - `partingLineCurves`: An array that contain a combination of sketch curves and BRepEdge objects to define the parting line.
    - `isChained`: If true, curves that are connected to any of the input parting line curves will also be included in the parting line.
- `setMovingPartingLineDraftFeatureType(partingLineCurves: list[Base], isChained: bool, direction: MovingPartingLineDirections, fixedEdges: list[BRepEdge]) -> bool` — ** This method is a preview feature and may change in future releases.
    - `partingLineCurves`: An array that contain a combination of sketch curves and BRepEdge objects to define the parting line.
    - `isChained`: If true, curves that are connected to any of the input parting line curves will also be included in the parting line.
    - `direction`: Specifies how the angle is calculated to determine how the parting line is moved.
    - `fixedEdges`: An array containing the edges that should not deform when the parting line moves.
- `setFixedPlaneDraftFeatureType() -> bool` — ** This method is a preview feature and may change in future releases.
- prop `inputFaces`: list[BRepFace] (rw) — Gets and sets the input faces.
- prop `plane`: Base (rw) — Gets and sets the plane that defines the direction in which the draft is applied.
- prop `isTangentChain`: bool (rw) — Gets and sets if any faces that are tangentially connected to any of the input faces will also be drafted.
- prop `isDirectionFlipped`: bool (rw) — Gets and sets if the direction of the draft is flipped.
- prop `draftDefinition`: ExtentDefinition (ro) — Gets the definition object that specifies how the draft is defined.
- prop `nativeObject`: DraftFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `draftType`: DraftFeatureTypes (ro) — ** This property is a preview feature and may change in future releases.
- prop `partingLineType`: PartingLineTypes (ro) — ** This property is a preview feature and may change in future releases.
- prop `movingPartingLineDirection`: MovingPartingLineDirections (ro) — ** This property is a preview feature and may change in future releases.
- prop `partingLineCurves`: list[Base] (ro) — ** This property is a preview feature and may change in future releases.
- prop `movingPartingLineFixedEdges`: list[BRepEdge] (ro) — ** This property is a preview feature and may change in future releases.

### EmbossFeature (Feature)
Object that represents an existing emboss feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> EmbossFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `profiles`: list[Base] (rw) — Gets and sets the set Profile objects that define the shape of the emboss.
- prop `inputFaces`: list[BRepFace] (rw) — Gets and sets an array of BRepFace objects that define the faces the emboss will be performed on.
- prop `isTangentChain`: bool (rw) — Gets and sets whether any faces that are tangentially connected to any of the input faces will also be used.
- prop `depth`: ModelParameter (ro) — Returns the parameter that controls the depth of the emboss.
- prop `horizontalDistance`: ModelParameter (ro) — Returns the parameter that controls the horizontal offset distance.
- prop `verticalDistance`: ModelParameter (ro) — Returns the parameter that controls the vertical offset distance.
- prop `rotationAngle`: ModelParameter (ro) — Returns the parameter that controls the rotation angle.
- prop `nativeObject`: EmbossFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### EqualDistanceChamferEdgeSet (ChamferEdgeSet)
Provides access to the edges and the parameter associated with a equal distance offset chamfer.
- prop `edges`: ObjectCollection (rw) — Gets and sets the edges that will be chamfered.
- prop `distance`: ModelParameter (ro) — Returns the model parameter that controls the offset distance of the chamfer.

### ExtendFeature (Feature)
Object that represents an existing extend feature in a design.
- `setInputEntities(edges: ObjectCollection, isChainingEnabled: bool = True) -> bool` — Sets the edges for the extend feature.
    - `edges`: The surface edges to extend.
    - `isChainingEnabled`: An optional boolean argument whose default is true.
- `createForAssemblyContext(occurrence: Occurrence) -> ExtendFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `edges`: ObjectCollection (ro) — Gets the edges that were extended.
- prop `distance`: ModelParameter (ro) — Returns the parameter controlling the extend distance.
- prop `extendType`: SurfaceExtendTypes (rw) — Gets and sets surface extend type to use.
- prop `isChainingEnabled`: bool (ro) — Gets if all edges that are tangent or curvature continuous, and end point connected, will be found automatically and extended.
- prop `nativeObject`: ExtendFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `extendAlignment`: SurfaceExtendAlignment (rw) — Gets and sets surface extend alignment to use.

### ExtrudeFeature (Feature)
Object that represents an existing extrude feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> ExtrudeFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `setOneSideExtent(extent: ExtentDefinition, direction: ExtentDirections, taperAngle: ValueInput = None) -> bool` — Redefines the extrusion to go in one direction from the profile.
    - `extent`: An ExtentDefinition object that defines how the extent of the extrusion is defined.
    - `direction`: Specifies the direction of the extrusion.
    - `taperAngle`: Optional argument that specifies the taper angle.
- `setTwoSidesExtent(sideOneExtent: ExtentDefinition, sideTwoExtent: ExtentDefinition, sideOneTaperAngle: ValueInput = None, sideTwoTaperAngle: ValueInput = None) -> bool` — Redefines the extrusion to go in both directions from the profile.
    - `sideOneExtent`: An ExtentDefinition object that defines how the extent of the extrusion towards side one is defined.
    - `sideTwoExtent`: An ExtentDefinition object that defines how the extent of the extrusion towards side two is defined.
    - `sideOneTaperAngle`: Optional argument that specifies the taper angle for side one.
    - `sideTwoTaperAngle`: Optional argument that specifies the taper angle for side two.
- `setSymmetricExtent(distance: ValueInput, isFullLength: bool, taperAngle: ValueInput = None) -> bool` — Redefines the extrusion to go symmetrically in both directions from the profile.
    - `distance`: The distance of the extrusions.
    - `isFullLength`: Defines if the value defines the full length of the extrusion or half of the length.
    - `taperAngle`: Optional argument that specifies the taper angle.
- `setThinExtrude(thinExtrudeWallLocationOne: ThinExtrudeWallLocation, thinExtrudeWallThicknessOne: ValueInput, thinExtrudeWallLocationTwo: ThinExtrudeWallLocation = ThinExtrudeWallLocation.Side1, thinExtrudeWallThicknessTwo: ValueInput = None) -> bool` — Changes the extrude feature to be a thin extrude.
    - `thinExtrudeWallLocationOne`: Specifies the position of the thin wall extrude with respect to the profile being extruded.
    - `thinExtrudeWallThicknessOne`: A ValueInput object that defines the thickness for a single sided thin extrude or side one of a two-sided extrusion .
    - `thinExtrudeWallLocationTwo`: Optional argument that specifies the position of side two of a two-sided extrusion.
    - `thinExtrudeWallThicknessTwo`: Optional argument that is a ValueInput object that defines the thickness for side two of a two-sided extrusion.
- prop `profile`: Base (rw) — Gets and sets the profiles or planar faces used to define the shape of the extrude.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the extrusion.
- prop `startFaces`: BRepFaces (ro) — Property that returns the set of faces that cap the end of the extrusion and are coincident with the sketch plane.
- prop `endFaces`: BRepFaces (ro) — Property that returns the set of faces that cap the end of the extrusion, opposite the start faces.
- prop `sideFaces`: BRepFaces (ro) — Property that returns all of the side faces (i.e.
- prop `nativeObject`: ExtrudeFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `isSolid`: bool (ro) — Indicates if this feature was initially created as a solid or a surface.
- prop `startExtent`: ExtentDefinition (rw) — Gets and sets the extent used to define the start of the extrusion.
- prop `extentOne`: ExtentDefinition (rw) — Gets and sets the extent used for a single sided extrude or side one of a two-sided extrusion.
- prop `extentTwo`: ExtentDefinition (rw) — Gets and sets the extent used for side two of the extrusion.
- prop `taperAngleOne`: ModelParameter (ro) — Gets the parameter controlling the taper angle for a single sided extrusion or side one of a two-sided extrusion.
- prop `taperAngleTwo`: ModelParameter (ro) — Gets the parameter controlling the taper angle for side two of a two-sided extrusion.
- prop `hasTwoExtents`: bool (ro) — Property that indicates if the extrusion is a single or two-sided extrusion.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `extentType`: FeatureExtentTypes (ro) — Returns a value indicating how the extent is defined for this extrude.
- prop `symmetricExtent`: SymmetricExtentDefinition (ro) — If the current extent of the feature is defined as a symmetric extent, this property returns the SymmericExtentDefinition object that provides access to the information defining the symmetric extent.
- prop `isThinExtrude`: bool (rw) — Sets or returns whether the extrude is a thin extrude.
- prop `thinExtrudeWallLocationOne`: ThinExtrudeWallLocation (rw) — Gets and sets the wall location for a one sided thin extrude or side one of a two sided thin extrude
- prop `thinExtrudeWallLocationTwo`: ThinExtrudeWallLocation (rw) — Gets and sets the wall location for side two of a two sided thin extrude
- prop `thinExtrudeWallThicknessOne`: ModelParameter (ro) — Gets and sets the wall thickness for a one sided thin extrude or side one of a two sided thin extrude
- prop `thinExtrudeWallThicknessTwo`: ModelParameter (ro) — Gets and sets the wall thickness for side two of a two sided thin extrude

### FilletFeature (Feature)
Object that represents an existing fillet feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> FilletFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `convert(input: Base) -> bool` — Method that converts this feature to another fillet feature type.
    - `input`: Input a fillet feature input object that defines the desired fillet.
- prop `edgeSets`: FilletEdgeSets (ro) — Returns the edge sets collection associated with this fillet.
- prop `isRollingBallCorner`: bool (rw) — Gets and sets if a rolling ball or setback solution is to be used in any corners.
- prop `nativeObject`: FilletFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `fullRoundFilletFaceSets`: FullRoundFilletFaceSets (ro) — Returns the full round fillet face sets collection associated with this fillet feature.
- prop `filletFeatureType`: FilletFeatureTypes (ro) — Returns the FilletFeatureTypes indicating this fillet feature type.
- prop `ruleFilletSettings`: RuleFilletSettings (ro) — Gets the RuleFilletSettings object for the rule fillet.

### FromEntityStartDefinition (ExtentDefinition)
A definition object that is used to define a feature whose start is defined by a specified construction plane or face.
- `create(entity: Base, offset: ValueInput) -> FromEntityStartDefinition` — Statically creates a new FromEntityStartDefinition object.
    - `entity`: An input construction plane or face that defines the start of the feature.
    - `offset`: An input ValueInput objects that defines the offset distance from the specified entity.
- prop `offset`: Base (ro) — Gets the currently defined offset value.
- prop `entity`: Base (rw) — Gets and sets the entity defining the start of the feature.

### HoleFeature (Feature)
Object that represents an existing hole feature in a design.
- `setToSimple() -> bool` — Calling this method will change the hole to a simple hole.
- `setToCounterbore(counterboreDiameter: ValueInput, counterboreDepth: ValueInput) -> bool` — Calling this method will change the hole to a counterbore hole.
    - `counterboreDiameter`: A ValueInput object that defines the counterbore diameter.
    - `counterboreDepth`: A ValueInput object that defines the counterbore depth.
- `setToCountersink(countersinkDiameter: ValueInput, countersinkAngle: ValueInput) -> bool` — Calling this method will change the hole to a countersink hole.
    - `countersinkDiameter`: A ValueInput object that defines the countersink diameter.
    - `countersinkAngle`: A ValueInput object that defines the countersink angle.
- `setDistanceExtent(distance: ValueInput) -> bool` — Defines the depth of the hole using a specific distance.
    - `distance`: The depth of the hole.
- `setAllExtent(direction: ExtentDirections) -> bool` — Defines the extent of the hole to be through-all.
    - `direction`: The direction of the hole relative to the normal of the sketch plane.
- `setOneSideToExtent(toEntity: Base, matchShape: bool, directionHint: Vector3D = None) -> bool` — Sets the extent of the hole to be from the sketch plane to the specified "to" face.
    - `toEntity`: The entity that defines the "to" extent.
    - `matchShape`: Indicates if the hole is not contained on the face that the hole should match the shape of the entity as if it extended beyond its current boundaries.
    - `directionHint`: Specifies the direction of the hole.
- `setPositionByPoint(planarEntity: Base, point: Base) -> bool` — Redefines the position of a the hole using a point.
    - `planarEntity`: The planar BRepFace or ConstructionPlane object that defines the orientation of the hole.
    - `point`: A Point3D object or vertex that defines the position of the hole.
- `setPositionAtCenter(planarEntity: Base, centerEdge: BRepEdge) -> bool` — Redefines the position of the hole at the center of a circular or elliptical edge of the face.
    - `planarEntity`: The planar BRepFace or ConstructionPlane object that defines the orientation of the hole.
    - `centerEdge`: A circular or elliptical edge whose center point will be the position of the hole.
- `setPositionBySketchPoint(sketchPoint: SketchPoint) -> bool` — Redefines the position and orientation of the hole using a sketch point.
    - `sketchPoint`: The sketch point that defines the position of the hole.
- `setPositionBySketchPoints(sketchPoints: ObjectCollection) -> bool` — Redefines the position and orientation of the hole using a set of points.
    - `sketchPoints`: A collection of sketch points that defines the positions of the holes.
- `setPositionByPlaneAndOffsets(planarEntity: Base, point: Point3D, edgeOne: BRepEdge, offsetOne: ValueInput, edgeTwo: BRepEdge = None, offsetTwo: ValueInput = None) -> bool` — Redefines the orientation of the hole using a planar face or construction plane.
    - `planarEntity`: The planar BRepFace or ConstructionPlane object that defines the orientation of the hole.
    - `point`: A Point3D object that defines the approximate initial position of the hole.
    - `edgeOne`: A linear BRepEdge object that the position of the hole will be measured from.
    - `offsetOne`: A ValueInput object that defines the offset distance from edgeOne.
    - `edgeTwo`: You can optionally define a second edge and offset to specify the position of the hole.
    - `offsetTwo`: If edgeTwo is defined, you must provide this argument which is a ValueInput object that defines the offset from the edgeTwo.
- `setPositionOnEdge(planarEntity: Base, edge: BRepEdge, position: HoleEdgePositions) -> bool` — Redefines the position and orientation of the hole to be on the start, end or center of an edge.
    - `planarEntity`: The planar BRepFace or ConstructionPlane object that defines the orientation of the hole and start of the hole.
    - `edge`: The edge to position the hole on.
    - `position`: The position along the edge to place the hole.
- `createForAssemblyContext(occurrence: Occurrence) -> HoleFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `setToSimpleHole() -> bool` — This method sets the hole's tap to be "simple," which means that the hole will not have any tap and will be a simple hole.
- `setToClearanceHole(clearanceHoleInfo: ClearanceHoleInfo) -> bool` — Sets the hole to be a clearance hole of the size specified by the ClearanceHoleInfo object.
    - `clearanceHoleInfo`: The ClearanceHoleInfo object that specifies the size of the clearance hole.
- `setToTappedHole(threadInfo: ThreadInfo) -> bool` — Sets the hole to be a straight or tapered tapped hole of the size specified by the ThreadInfo object.
    - `threadInfo`: The ThreadInfo object that specifies the thread to use for the tapped hole.
- prop `position`: Point3D (ro) — Returns the position of the hole.
- prop `direction`: Vector3D (ro) — Returns the direction of the hole.
- prop `holeType`: HoleTypes (ro) — Returns the current type of hole this feature represents.
- prop `holeDiameter`: ModelParameter (ro) — Returns the model parameter controlling the hole diameter.
- prop `tipAngle`: ModelParameter (ro) — Returns the model parameter controlling the angle of the tip of the hole.
- prop `counterboreDiameter`: ModelParameter (ro) — Returns the model parameter controlling the counterbore diameter.
- prop `counterboreDepth`: ModelParameter (ro) — Returns the model parameter controlling the counterbore depth.
- prop `countersinkDiameter`: ModelParameter (ro) — Returns the model parameter controlling the countersink diameter.
- prop `countersinkAngle`: ModelParameter (ro) — Returns the model parameter controlling the countersink angle.
- prop `isDefaultDirection`: bool (rw) — Gets and sets if the hole is in the default direction or not.
- prop `extentDefinition`: ExtentDefinition (ro) — Gets the definition object that is defining the extent of the hole.
- prop `endFaces`: BRepFaces (ro) — Property that returns the faces at the bottom of the hole.
- prop `sideFaces`: BRepFaces (ro) — Property that returns all of the side faces of the hole.
- prop `holePositionDefinition`: HolePositionDefinition (ro) — Returns a HolePositionDefinition object that provides access to the information used to define the position of the hole.
- prop `nativeObject`: HoleFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `holeTapType`: HoleTapTypes (ro) — This property returns the current type of tap associated with this hole.
- prop `clearanceHoleInfo`: ClearanceHoleInfo (ro) — Returns the information used to define a clearance hole.
- prop `tappedHoleInfo`: ThreadInfo (ro) — This property returns the information used to define a tapped hole.
- prop `thread`: ThreadFeature (ro) — When a tapped hole is created, a thread feature is also automatically created and controls the tapped threads.

### LoftDirectionEndCondition (LoftEndCondition)
Represents a "Direction" loft end condition.
- prop `angle`: Base (ro) — Gets the valueInput or Parameter that defines the angle of the direction of the loft.
- prop `weight`: Base (ro) — Gets the valueInput or Parameter that defines the weight of the loft.

### LoftedFlangeFeature (Feature)
** This class is a preview feature and may change in future releases.
- `setFacetControlByChordTolerance(chordTolerance: ValueInput) -> bool` — Changes the facet control to chord tolerance and sets the value.
    - `chordTolerance`: The maximum allowable chord tolerance distance.
- `setFacetControlByFacetAngle(facetAngle: ValueInput) -> bool` — Changes the facet control to facet angle and sets the value.
    - `facetAngle`: The maximum allowable angle between adjacent facet normals.
- `setFacetControlByFacetDistance(facetDistance: ValueInput) -> bool` — Changes the facet control to facet distance and sets the value.
    - `facetDistance`: The maximum allowable facet edge length.
- `setFacetControlByFacetNumber(facetNumber: ValueInput) -> bool` — Changes the facet control to a fixed number of facets and sets the value.
    - `facetNumber`: The number of facets.
- `createForAssemblyContext(occurrence: Occurrence) -> LoftedFlangeFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `profiles`: list[Profile] (rw) — Gets and sets the ordered array of open profiles that define the cross-sections of the lofted flange.
- prop `orientation`: FlangeOrientations (rw) — Gets and sets the orientation of the lofted flange, defining on which side of the profile planes the material thickness is applied.
- prop `formingType`: LoftedFlangeFormingTypes (rw) — Gets and sets the forming type for the lofted flange, which controls how the sheet metal is physically formed between the profiles.
- prop `facetControlType`: LoftedFlangeFacetControlTypes (ro) — Gets the facet control type currently active on this lofted flange feature.
- prop `facetControlParameter`: ModelParameter (ro) — Returns the model parameter that controls the faceting approximation.
- prop `operation`: FeatureOperations (ro) — Gets the type of operation performed by this lofted flange feature.
- prop `nativeObject`: LoftedFlangeFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### LoftFeature (Feature)
Object that represents an existing loft feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> LoftFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `loftSections`: LoftSections (ro) — Returns the set of sections that the loft passes through.
- prop `centerLineOrRails`: LoftCenterLineOrRails (ro) — Returns the single centerline or the set of rails that define the shape of the loft.
- prop `startFace`: BRepFace (ro) — Property that returns the face that caps the start of the loft and is coincident with the first section.
- prop `endFace`: BRepFace (ro) — Property that returns the face that caps the end of the loft and is coincident with the last section.
- prop `sideFaces`: BRepFaces (ro) — Property that returns all of the side faces (i.e.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the extrusion.
- prop `isSolid`: bool (ro) — Indicates if this feature was initially created as a solid or a surface.
- prop `nativeObject`: LoftFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `isClosed`: bool (rw) — Specifies if the loft closes back on itself.
- prop `isTangentEdgesMerged`: bool (rw) — Specifies if the loft will keep or merge tangent edges.
- prop `startLoftEdgeAlignment`: LoftEdgeAlignments (rw) — Specifies the start edge alignment option for the loft feature.
- prop `endLoftEdgeAlignment`: LoftEdgeAlignments (rw) — Specifies the end edge alignment option for the loft feature.

### LoftFreeEndCondition (LoftEndCondition)
Represents a "Free" loft end condition.

### LoftPointSharpEndCondition (LoftEndCondition)
Represents a "Point Sharp" loft end condition.

### LoftPointTangentEndCondition (LoftEndCondition)
Represents a "Point Tangent" loft end condition.
- prop `weight`: Base (ro) — Gets the valueInput or Parameter that defines the weight of the loft.

### LoftSmoothEndCondition (LoftEndCondition)
Represents a "Smooth" loft end condition.
- prop `weight`: Base (ro) — Gets the valueInput or Parameter that defines the weight of the loft.

### LoftTangentEndCondition (LoftEndCondition)
Represents a "Tangent" loft end condition.
- prop `weight`: Base (ro) — Gets the valueInput or Parameter that defines the weight of the loft.

### MirrorFeature (Feature)
Object that represents an existing mirror feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> MirrorFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the entities to mirror using an ObjectCollection.
- prop `mirrorPlane`: Base (rw) — Gets and sets the mirror plane.
- prop `patternElements`: PatternElements (ro) — Gets the PatternElements collection that contains the elements created by this pattern.
- prop `resultFeatures`: ObjectCollection (ro) — Get the features that were created for this mirror.
- prop `nativeObject`: MirrorFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `patternComputeOption`: PatternComputeOptions (rw) — Gets and sets the compute option for this mirror feature.
- prop `isCombine`: bool (rw) — Gets and sets whether combine is set when doing the Mirror.
- prop `stitchTolerance`: ModelParameter (ro) — Returns the parameter controlling the Stitch tolerance to use when stitching mirrored surface bodies with the original bodies.

### ModelParameter (Parameter)
Represents a Model Parameter.
- `deleteMe() -> bool` — Deletes this ModelParameter.
- prop `modelParameters`: ModelParameters (ro) — Returns the Collection containing the ModelParameter.
- prop `component`: Component (ro) — Returns the Component containing the ModelParameter.
- prop `role`: str (ro) — This property identifies what the parameter is used for.
- prop `createdBy`: Base (ro) — Returns the object that created this parameter.

### MoveFeature (Feature)
Object that represents an existing move feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> MoveFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `redefineAsFreeMove(transform: Matrix3D) -> bool` — Redefines the move feature to be described by an arbitrary translation and orientation which is defined using a transformation matrix.
    - `transform`: The transformation matrix that defines the transform to apply.
- `redefineAsTranslateXYZ(xDistance: ValueInput, yDistance: ValueInput, zDistance: ValueInput, isDesignSpace: bool) -> bool` — Redefines the move feature to be described by a translation in X, Y, and Z.
    - `xDistance`: A ValueInput object that defines the offset in the X direction.
    - `yDistance`: A ValueInput object that defines the offset in the Y direction.
    - `zDistance`: A ValueInput object that defines the offset in the Z direction.
    - `isDesignSpace`: Defines if the translation is defined with respect to the design or component space.
- `redefineAsTranslateAlongEntity(linearEntity: Base, distance: ValueInput) -> bool` — Redefines the move feature to be a translation along a specified entity.
    - `linearEntity`: A linear entity that defines the direction of the move.
    - `distance`: A ValueInput object that defines the offset distance.
- `redefineAsRotate(axisEntity: Base, angle: ValueInput) -> bool` — Redefines the move feature to be described by an axis and rotation angle.
    - `axisEntity`: A linear entity that defines the axis of rotation.
    - `angle`: A ValueInput object that defines the rotation angle.
- `redefineAsPointToPoint(originPoint: Base, targetPoint: Base) -> bool` — Redefines the move feature to be a translation from one point to another.
    - `originPoint`: The first point that defines the start position of the move.
    - `targetPoint`: The second point that defines the direction and distance of the move.
- `redefineAsPointToPosition(point: Base, xDistance: ValueInput, yDistance: ValueInput, zDistance: ValueInput, isDesignSpace: bool) -> bool` — Redefines a move feature to be described by a point and an offset.
    - `point`: An entity that defines a point in space.
    - `xDistance`: A ValueInput object that defines the offset in the X direction.
    - `yDistance`: A ValueInput object that defines the offset in the Y direction.
    - `zDistance`: A ValueInput object that defines the offset in the Z direction.
    - `isDesignSpace`: Defines if the translation is defined with respect to the design or component space.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the entities to move.
- prop `nativeObject`: MoveFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `definition`: MoveFeatureDefinition (ro) — Returns the MoveFeatureDefinition object which provides access to the information that specifies how this MoveFeature is defined.

### MoveFeatureFreeMoveDefinition (MoveFeatureDefinition)
The MoveFeatureFreeMoveDefinition object defines a move feature described by a transformation matrix.
- prop `transform`: Matrix3D (rw) — Gets and sets the transform that's applied to the face or body.

### MoveFeaturePointToPointDefinition (MoveFeatureDefinition)
The MoveFeaturePointToPointDefinition object defines a move feature described by the translation from one point to another.
- prop `originPoint`: Base (rw) — Gets and sets the first point that defines the start position of the move.
- prop `targetPoint`: Base (rw) — Gets and sets the second point that defines the direction and distance of the move.

### MoveFeaturePointToPositionDefinition (MoveFeatureDefinition)
The MoveFeaturePointToPositionDefinition object defines a move feature described by a point and an offset.
- prop `point`: Base (rw) — Gets and sets the entity that defines a point in space.
- prop `xDistance`: ModelParameter (ro) — Gets the model parameter that controls the offset in the X direction.
- prop `yDistance`: ModelParameter (ro) — Gets the model parameter that controls the offset in the Y direction.
- prop `zDistance`: ModelParameter (ro) — Gets the model parameter that controls the offset in the Z direction.
- prop `isDesignSpace`: bool (rw) — Gets and sets if the translation is defined with respect to the design or component space.

### MoveFeatureRotateDefinition (MoveFeatureDefinition)
The MoveFeatureRotateDefinition object defines a move feature described by a rotation around a specified entity.
- prop `axisEntity`: Base (rw) — Gets and sets the linear entity that defines the axis of rotation.
- prop `angle`: ModelParameter (ro) — Gets the model parameter that controls the rotation angle.

### MoveFeatureTranslateAlongEntityDefinition (MoveFeatureDefinition)
The MoveFeatureTranslateAlongEntityDefinition object defines a move feature described by a translation in the direction defined by a specified entity.
- prop `linearEntity`: Base (rw) — Gets and sets the linear entity that defines the direction of the move.
- prop `distance`: ModelParameter (ro) — Gets the model parameter that controls the offset distance.

### MoveFeatureTranslateXYZDefinition (MoveFeatureDefinition)
The MoveFeatureTranslateXYZDefinition object defines a move feature described by offsets in the X, Y, and Z directions.
- prop `xDistance`: ModelParameter (ro) — Gets the model parameter that controls the X distance of the translation.
- prop `yDistance`: ModelParameter (ro) — Gets the model parameter that controls the Y distance of the translation.
- prop `zDistance`: ModelParameter (ro) — Gets the model parameter that controls the Z distance of the translation.
- prop `isDesignSpace`: bool (rw) — Gets and sets if the translation is defined with respect to the design or component space.

### OffsetConstraint (GeometricConstraint)
An offset constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> OffsetConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `parentCurves`: list[SketchCurve] (ro) — Returns an array of sketch curves that are the set of parent curves.
- prop `childCurves`: list[SketchCurve] (ro) — Returns an array of sketch curves that are the set of child curves resulting from the offset.
- prop `distance`: float (ro) — The current distance of the offset in centimeters.
- prop `dimension`: SketchDimension (ro) — Returns the dimension controlling the offset distance.
- prop `nativeObject`: OffsetConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `isTopologyMatched`: bool (ro) — Gets the setting that controls if the offset curves match the topology of the original curves.

### OffsetFacesFeature (Feature)
Object that represents an existing Offset Faces feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> OffsetFacesFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `distance`: ModelParameter (ro) — Returns the parameter that controls the offset distance.
- prop `inputFaces`: list[BRepFace] (rw) — Returns an array of BRepFace objects that were offset.
- prop `nativeObject`: OffsetFacesFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### OffsetFeature (Feature)
Object that represents an existing offset feature in a design.
- `setInputEntities(entities: ObjectCollection, isChainSelection: bool = True) -> bool` — Sets the faces and sheet bodies to offset.
    - `entities`: An ObjectCollection containing the BRepFace objects to offset.
    - `isChainSelection`: A boolean value for setting whether or not faces that are tangentially connected to the input faces (if any) will also be offset.
- `createForAssemblyContext(occurrence: Occurrence) -> OffsetFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entities`: ObjectCollection (rw) — Gets and sets the faces to be offset.
- prop `isChainSelection`: bool (ro) — Get if the faces that are tangentially connected to the input faces (if any) are also offset.
- prop `distance`: ModelParameter (ro) — Returns the parameter controlling the offset distance.
- prop `operation`: FeatureOperations (ro) — Gets the feature operation that was performed when the feature was created, (either 'NewBodyFeatureOperation' or 'NewComponentFeatureOperation'.
- prop `nativeObject`: OffsetFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `offsetType`: OffsetTypes (rw) — Gets and sets the offset type for the offset.

### OffsetStartDefinition (ExtentDefinition)
A definition object that is used to define a feature whose start plane is defined as plane that is offset from the sketch plane of the profile.
- `create(offset: ValueInput) -> OffsetStartDefinition` — Statically creates a new OffsetStartDefinition object.
    - `offset`: An input ValueInput objects that defines the offset distance.
- prop `offset`: Base (ro) — Gets the currently defined offset value.
- prop `profilePlane`: Plane (ro) — Returns the geometric definition of the profile plane.

### PatchFeature (Feature)
An object that represents an existing patch feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> PatchFeature` — Creates or returns a proxy for the native object - i.e., a new object that represents this object but adds the assembly context defined by the input occurrence.
    - `occurrence`: The occurrence that defines the context to create the proxy.
- `setContinuity(continuity: list[int], weight: list[float], isContinuityDirectionFlipped: list[bool]) -> bool` — Sets the continuity to use for each edge in the boundary.
    - `continuity`: An array whose size of the number of B-Rep edges in the boundary.
    - `weight`: An array whose size is the number of B-Rep edges in the boundary.
    - `isContinuityDirectionFlipped`: An array whose size is the number of B-Rep edges in the boundary.
- `getContinuity() -> tuple[bool, list[BRepEdge], list[int], list[float], list[bool]]` — Gets the continuity used for each edge in the boundary.
    - `edges`: Output array containing all of the BRepEdge objects in the boundary.
    - `continuity`: Output array the same size as the edges array that defines the continuity to apply to the edge in the same index in the edges array.
    - `weight`: Output array the same size as the edges array that defines the weight applied to the edge in the same index in the edges array.
    - `isContinuityDirectionFlipped`: Output array the same size as the edges array that defines which of the two faces the edge connects to is used in computing the continuity direction.
- prop `boundaryCurve`: Base (rw) — Returns an ObjectCollection that contains all of the sketch curves or B-Rep edges that defines the closed outer boundary of the patch feature.
- prop `operation`: FeatureOperations (ro) — Gets the type of operation performed by the patch feature.
- prop `nativeObject`: PatchFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `interiorRailsAndPoints`: ObjectCollection (rw) — Gets and sets any interior curves or points the patch should fit through.
- prop `isGroupEdges`: bool (rw) — Gets and sets if the edges in the boundary curve are treated as a group , and they all use the same continuity.
- prop `groupContinuity`: SurfaceContinuityTypes (rw) — Gets and sets the type of surface continuity to use for all edges when the isGroupEdges property is true.
- prop `groupWeight`: float (rw) — Gets and sets the weight to use for all edges when the isGroupEdges property is true.
- prop `groupIsContinuityDirectionFlipped`: bool (rw) — Gets and sets the continuity direction for all edges when the isGroupEdges property is true.

### PathPatternFeature (Feature)
Object that represents an existing path pattern feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> PathPatternFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the entities to pattern using an ObjectCollection.
- prop `path`: Path (rw) — Gets and sets the path to create the pattern on path.
- prop `quantity`: ModelParameter (ro) — Gets the quantity of the elements.
- prop `distance`: ModelParameter (ro) — Gets the distance.
- prop `startPoint`: float (rw) — Gets and sets the start point on the path to count the distance.
- prop `isFlipDirection`: bool (rw) — Gets and sets if flip the direction from start point.
- prop `patternDistanceType`: PatternDistanceType (rw) — Gets and sets how the distance between elements is computed.
- prop `isSymmetric`: bool (rw) — Gets and sets if the pattern is in one direction or symmetric.
- prop `isOrientationAlongPath`: bool (rw) — Gets and sets if the orientation is along path.
- prop `suppressedElementsIds`: list[int] (rw) — Gets and sets the id's of the elements to suppress.
- prop `patternElements`: PatternElements (ro) — Gets the PatternElements collection that contains the elements created by this pattern.
- prop `resultFeatures`: ObjectCollection (ro) — Get the features that were created for this mirror.
- prop `nativeObject`: PathPatternFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `patternEntityType`: PatternEntityTypes (ro) — Returns the type of entities the pattern consists of.
- prop `patternComputeOption`: PatternComputeOptions (rw) — Gets and sets the compute option for this pattern feature.

### PipeFeature (Feature)
Object that represents an existing pipe feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> PipeFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `setThickness(value: ValueInput) -> bool` — Defines the section thickness of the Pipe.
- prop `nativeObject`: PipeFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the Pipe.
- prop `path`: Path (rw) — Gets and sets the path to create the Pipe.
- prop `distanceOne`: ModelParameter (ro) — Gets the distance for the pipe created while following the path given as input, in the same order.
- prop `distanceTwo`: ModelParameter (ro) — Gets the distance for the pipe created while following the reversed path given as input.
- prop `sectionType`: PipeSectionTypes (rw) — Gets and sets the section type of the Pipe.
- prop `sectionSize`: ModelParameter (ro) — Gets and sets the section size of the Pipe.
- prop `isHollow`: bool (rw) — Specifies if the Pipe is hollow or not.
- prop `sectionThickness`: ModelParameter (ro) — Gets the section thickness of the Pipe.
- prop `startFaces`: BRepFaces (ro) — Property that returns the set of faces that cap one end of the Pipe that are coincident with the sketch plane.
- prop `endFaces`: BRepFaces (ro) — Property that returns the set of faces that cap one end of the Pipe that are coincident with the sketch plane.
- prop `sideFaces`: BRepFaces (ro) — Property that returns an object that provides access to all of the faces created around the perimeter of the feature.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.

### ProfilePlaneStartDefinition (ExtentDefinition)
A definition object that is used to define a feature whose start plane is the sketch plane of the profile.
- `create() -> ProfilePlaneStartDefinition` — Statically creates a new ProfilePlaneStartDefinition object.
- prop `profilePlane`: Plane (ro) — Returns the geometric definition of the profile plane.

### RectangularPatternConstraint (GeometricConstraint)
A rectangular pattern constraint in a sketch.
- `setDirectionOne(directionOneEntity: SketchLine, quantityOne: ValueInput, distanceOne: ValueInput) -> bool` — Sets all of the input required to define the pattern in the first direction.
    - `directionOneEntity`: Specifies the SketchLine object used to define the first direction entity.
    - `quantityOne`: Specifies the number of instances in the first direction.
    - `distanceOne`: Specifies the distance in the first direction.
- `setDirectionTwo(directionTwoEntity: SketchLine, quantityTwo: ValueInput, distanceTwo: ValueInput) -> bool` — Sets all of the input required to define the pattern in the second direction.
    - `directionTwoEntity`: Specifies the SketchLine object used to define the second direction entity.
    - `quantityTwo`: Specifies the number of instances in the second direction.
    - `distanceTwo`: Specifies the distance in the second direction.
- `createForAssemblyContext(occurrence: Occurrence) -> RectangularPatternConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entities`: list[SketchEntity] (rw) — Gets and sets the entities that are patterned.
- prop `createdEntities`: list[SketchEntity] (ro) — Returns an array that contains all of the sketch entities that were created as a result of the pattern.
- prop `directionOneEntity`: SketchLine (rw) — Gets and sets the entity that defined the first direction of the pattern.
- prop `directionTwoEntity`: SketchLine (rw) — Gets and sets the entity that defines the second direction of the pattern.
- prop `quantityOne`: ModelParameter (ro) — Returns the parameter that controls the number of instances in the first direction.
- prop `quantityTwo`: ModelParameter (ro) — Returns the parameter that controls the number of instances in the second direction.
- prop `distanceOne`: ModelParameter (ro) — Returns the parameter that controls the distance in first direction.
- prop `distanceTwo`: ModelParameter (ro) — Returns the parameter that controls the distance in second direction.
- prop `isSymmetricInDirectionOne`: bool (rw) — Gets and sets if the pattern in direction one is in one direction or is symmetric.
- prop `isSymmetricInDirectionTwo`: bool (rw) — Gets and sets if the pattern in direction two is in one direction or is symmetric.
- prop `distanceType`: PatternDistanceType (rw) — Gets and sets how the distance between elements is computed.
- prop `isSuppressed`: list[bool] (rw) — Specifies which, if any, instances of the pattern are suppressed.
- prop `nativeObject`: RectangularPatternConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### RectangularPatternFeature (Feature)
Object that represents an existing rectangular pattern feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> RectangularPatternFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the entities to pattern using an ObjectCollection.
- prop `directionOneEntity`: Base (rw) — Gets and sets the first direction entity.
- prop `directionTwoEntity`: Base (rw) — Gets and sets the second direction entity.
- prop `directionOne`: Vector3D (ro) — Returns a Vector3D indicating the positive direction of direction one.
- prop `directionTwo`: Vector3D (ro) — Returns a Vector3D indicating the positive direction of direction two.
- prop `quantityOne`: ModelParameter (ro) — Gets the number of instances in the first direction.
- prop `quantityTwo`: ModelParameter (ro) — Gets the number of instances in the second direction.
- prop `distanceOne`: ModelParameter (ro) — Gets the distance in the first direction.
- prop `distanceTwo`: ModelParameter (ro) — Gets the distance in the second direction.
- prop `isSymmetricInDirectionOne`: bool (rw) — Gets and sets if the pattern in direction one is in one direction or symmetric.
- prop `isSymmetricInDirectionTwo`: bool (rw) — Gets and sets if the pattern in direction two is in one direction or symmetric.
- prop `patternDistanceType`: PatternDistanceType (rw) — Gets and sets how the distance between elements is computed.
- prop `suppressedElementsIds`: list[int] (rw) — Gets and sets the ids of the patterns to suppress.
- prop `patternElements`: PatternElements (ro) — Gets the PatternElements collection that contains the elements created by this pattern.
- prop `resultFeatures`: ObjectCollection (ro) — Get the features that were created for this pattern.
- prop `nativeObject`: RectangularPatternFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `patternEntityType`: PatternEntityTypes (ro) — Returns the type of entities the pattern consists of.
- prop `patternComputeOption`: PatternComputeOptions (rw) — Gets and sets the compute option for this pattern feature.

### RemoveFeature (Feature)
Object that represents an existing Remove feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> RemoveFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `itemToRemove`: Base (ro) — Gets and sets the body or component occurrence to remove.
- prop `nativeObject`: RemoveFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### ReplaceFaceFeature (Feature)
Object that represents an existing replace face feature in a design.
- `setInputEntities(sourceFaces: ObjectCollection, isTangentChain: bool) -> bool` — Method that sets faces to replace.
    - `sourceFaces`: The collection can contain the faces from a solid and/or from features.
    - `isTangentChain`: A boolean value for setting whether or not faces that are tangentially connected to the input faces (if any) will also be included.
- `createForAssemblyContext(occurrence: Occurrence) -> ReplaceFaceFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `targetFaces`: Base (rw) — Gets and sets the entities that define the target faces.
- prop `isTangentChain`: bool (ro) — Gets if any faces that are tangentially connected to any of the input faces will also be included in setting InputEntities.
- prop `nativeObject`: ReplaceFaceFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### RevolveFeature (Feature)
Object that represents an existing revolve feature in a design.
- `setAngleExtent(isSymmetric: bool, angle: ValueInput) -> bool` — Defines the extent of the revolution to be at a defined angle.
    - `isSymmetric`: Boolean that specifies if the extent is symmetric or not.
    - `angle`: ValueInput object that defines the angle.
- `setTwoSideAngleExtent(angleOne: ValueInput, angleTwo: ValueInput) -> bool` — Changes the extent of the revolve to be defined as a two sided angle extent.
    - `angleOne`: ValueInput object that defines the first angle.
    - `angleTwo`: ValueInput object that defines the second angle.
- `setOneSideToExtent(toEntity: Base, directionHint: Vector3D = None) -> bool` — Changes the extent of the revolve to be from the sketch plane to the specified "to" face.
    - `toEntity`: The entity that defines the "to" extent.
    - `directionHint`: Specifies the direction of the revolve.
- `setTwoSidesToExtent(toEntityOne: Base, toEntityTwo: Base) -> bool` — Changes the extent of the revolve to be defined as a two sided to extent.
    - `toEntityOne`: The first entity that defines the "to" extent.
    - `toEntityTwo`: The second entity that defines the "to" extent.
- `createForAssemblyContext(occurrence: Occurrence) -> RevolveFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `profile`: Base (rw) — Gets and sets the profiles or planar faces used to define the shape of the revolve.
- prop `axis`: Base (rw) — Gets and sets the entity used to define the axis of revolution.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the revolve.
- prop `extentDefinition`: ExtentDefinition (ro) — Gets the definition object that is defining the extent of the revolve.
- prop `startFaces`: BRepFaces (ro) — Property that returns the set of faces that cap one end of the revolve and are coincident with the sketch plane.
- prop `endFaces`: BRepFaces (ro) — Property that returns the set of faces that cap the end of the revolve opposite the start faces.
- prop `sideFaces`: BRepFaces (ro) — Property that returns all of the faces created around the perimeter of the feature.
- prop `nativeObject`: RevolveFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `isSolid`: bool (ro) — Indicates if this feature was initially created as a solid or a surface.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `isProjectAxis`: bool (rw) — Specifies if the axis should be projected on the same plane as the profile sketch plane or not.

### RibFeature (Feature)
Object that represents an existing Rib feature in a design.

### RuledSurfaceFeature (Feature)
Object that represents an existing RuledSurface feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> RuledSurfaceFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `profile`: Base (rw) — Gets and sets the Profile object that defines the sketch geometry or edges that define the shape of the ruled surface.
- prop `distance`: ModelParameter (ro) — Returns the parameter controlling the Ruled Surface distance.
- prop `angle`: ModelParameter (ro) — Returns the parameter controlling the Ruled Surface angle.
- prop `ruledSurfaceType`: RuledSurfaceTypes (rw) — Gets and sets the type of ruled surface.
- prop `direction`: Base (rw) — Gets and sets the entity that defines the direction when the ruled surface type is DirectionRuledSurfaceType.
- prop `alternateFace`: bool (rw) — Gets and sets if the other face is used for creation of the Ruled Surface.
- prop `nativeObject`: RuledSurfaceFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `cornerType`: RuledSurfaceCornerTypes (rw) — Gets and sets the corner type for the ruled surface, indicating if the corners will be rounded or mitered.

### ScaleFeature (Feature)
Object that represents an existing scale feature in a design.
- `setToUniform(scaleFactor: ValueInput) -> bool` — Calling this method will change to a uniform scale.
    - `scaleFactor`: A ValueInput object that defines the scale factor.
- `setToNonUniform(xScale: ValueInput, yScale: ValueInput, zScale: ValueInput) -> bool` — Calling this method will change to a non-uniform scale.
    - `xScale`: A ValueInput object that defines the scale in the X direction.
    - `yScale`: A ValueInput object that defines the scale in the Y direction.
    - `zScale`: A ValueInput object that defines the scale in the Z direction.
- `createForAssemblyContext(occurrence: Occurrence) -> ScaleFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `inputEntities`: ObjectCollection (rw) — Gets and sets the input entities.
- prop `point`: Base (rw) — Gets and sets the point as reference to scale.
- prop `isUniform`: bool (ro) — Gets if it's uniform scale.
- prop `scaleFactor`: ModelParameter (ro) — Returns the parameter that controls the uniform scale factor.
- prop `xScale`: ModelParameter (ro) — Returns the parameter that controls the X scale factor.
- prop `yScale`: ModelParameter (ro) — Returns the parameter that controls the Y scale factor.
- prop `zScale`: ModelParameter (ro) — Returns the parameter that controls the Z scale factor.
- prop `nativeObject`: ScaleFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### ShellFeature (Feature)
Object that represents an existing shell feature in a design.
- `setInputEntities(inputEntities: ObjectCollection, isTangentChain: bool = True) -> bool` — Method that sets faces to remove and bodies to preform shell.
    - `inputEntities`: The collection contains the faces to remove and the bodies to perform shell.
    - `isTangentChain`: A boolean value for setting whether or not faces that are tangentially connected to the input faces (if any) will also be included.
- `setThicknesses(insideThickness: ValueInput, outsideThickness: ValueInput) -> bool` — Method that sets the inside and outside thicknesses of the shell.
    - `insideThickness`: ValueInput object that defines the inside thickness.
    - `outsideThickness`: ValueInput object that defines the outside thickness.
- `createForAssemblyContext(occurrence: Occurrence) -> ShellFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `inputEntities`: ObjectCollection (ro) — Gets the input faces/bodies.
- prop `isTangentChain`: bool (ro) — Gets if any faces that are tangentially connected to any of the input faces will also be included in setting InputEntities.
- prop `insideThickness`: ModelParameter (ro) — Gets the inside thickness.
- prop `outsideThickness`: ModelParameter (ro) — Gets the outside thickness.
- prop `nativeObject`: ShellFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `shellType`: ShellTypes (rw) — The shell type used when creating a shell.

### SplitBodyFeature (Feature)
Object that represents an existing split body feature in a design.
- `setSplittingTool(splittingTool: Base, isSplittingToolExtended: bool) -> bool` — Sets the splitting tool used for the feature.
    - `splittingTool`: Input entity that defines the splitting tool.
    - `isSplittingToolExtended`: A boolean value for setting whether or not the splittingTool is to be automatically extended (if possible) so as to completely intersect the facesToSplit.
- `createForAssemblyContext(occurrence: Occurrence) -> SplitBodyFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `splitBodies`: ObjectCollection (rw) — Gets and sets the input solid or open bodies that are split.
- prop `splittingTool`: Base (ro) — Gets the entity that defines the splitting tool.
- prop `isSplittingToolExtended`: bool (ro) — Gets whether or not the splitting tool is to be automatically extended (if possible) so as to completely intersect the bodyToSplit.
- prop `nativeObject`: SplitBodyFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SplitFaceFeature (Feature)
Object that represents an existing split face feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> SplitFaceFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `setAsSurfaceIntersectionSplitType(splittingTool: Base, isSplittingToolExtended: bool) -> bool` — Set the split type to be a surface to surface intersection.
    - `splittingTool`: Input entity(s) that defines the splitting tool.
    - `isSplittingToolExtended`: Specifies if the splitting tool should be extended so that is fully intersects the faces to be split.
- `setAsAlongVectorSplitType(splittingTool: Base, directionEntity: Base) -> bool` — Sets the split type to project the splitting tool along the direction defined by the specified entity.
    - `splittingTool`: Input entity(s) that defines the splitting tool.
    - `directionEntity`: An entity that defines the direction of projection of the splitting tool.
- `setAsClosestPointSplitType(splittingTool: Base) -> bool` — Sets the split type to be a curve that defined by projecting the splitting curve to the closest point on the surface.
    - `splittingTool`: Input entity(s) that defines the splitting tool.
- prop `facesToSplit`: ObjectCollection (rw) — Gets and sets the faces to be split.
- prop `splittingTool`: ObjectCollection (ro) — Gets the entity(s) that define the splitting tool(s).
- prop `isSplittingToolExtended`: bool (ro) — Gets whether or not the setting to automatically extend the splittingTool was set when the feature was created.
- prop `nativeObject`: SplitFaceFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `directionEntity`: Base (ro) — Gets the direction entity when the split type is along a vector.
- prop `splitType`: SplitFaceSplitTypes (ro) — Returns the type of split type currently defined.

### StitchFeature (Feature)
Object that represents an existing stitch feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> StitchFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `stitchSurfaces`: ObjectCollection (rw) — Gets and sets the surfaces to stitch together.
- prop `tolerance`: ModelParameter (ro) — Returns the parameter controlling the tolerance.
- prop `operation`: FeatureOperations (rw) — Gets and sets the feature operation to perform.
- prop `nativeObject`: StitchFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SweepFeature (Feature)
Object that represents an existing sweep feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> SweepFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `profile`: Base (rw) — Gets and sets the profiles or planar faces used to define the shape of the sweep.
- prop `operation`: FeatureOperations (rw) — Gets and sets the type of operation performed by the sweep.
- prop `path`: Path (rw) — Gets and sets the path to create the sweep.
- prop `distanceOne`: ModelParameter (ro) — Gets the distance for the first side.
- prop `distanceTwo`: ModelParameter (ro) — Gets the distance for the second side.
- prop `orientation`: SweepOrientationTypes (rw) — Gets and sets the sweep orientation.
- prop `startFaces`: BRepFaces (ro) — Property that returns the set of that cap one end of the sweep that are coincident with the sketch plane.
- prop `endFaces`: BRepFaces (ro) — Property that returns the set of that cap one end of the sweep that are coincident with the sketch plane.
- prop `sideFaces`: BRepFaces (ro) — Property that returns an object that provides access to all of the faces created around the perimeter of the feature.
- prop `nativeObject`: SweepFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `isSolid`: bool (ro) — Indicates if this feature was initially created as a solid or a surface.
- prop `guideRail`: Path (rw) — Gets and sets the guide rail to create the sweep.
- prop `isDirectionFlipped`: bool (rw) — Gets and sets if the direction of the sweep is flipped.
- prop `profileScaling`: SweepProfileScalingOptions (rw) — Gets and sets the sweep profile scaling option.
- prop `participantBodies`: list[BRepBody] (rw) — Gets and sets the list of bodies that will participate in the feature when the operation is a cut or intersection.
- prop `taperAngle`: ModelParameter (ro) — Gets the ModelParameter that defines the taper angle of the sweep feature.
- prop `twistAngle`: ModelParameter (ro) — Gets the ModelParameter that defines the twist angle of the sweep feature.
- prop `extent`: SweepExtentTypes (rw) — Gets and sets the sweep extent type.
- prop `guideSurfaces`: list[BRepFace] (rw) — Gets and sets the guide surfaces to create the sweep.
- prop `isChainSelection`: bool (rw) — Get and sets whether faces that are tangentially connected to the guide surfaces are also made guide surfaces.
- prop `solidBody`: BRepBody (rw) — Gets and sets the BRepBody object to sweep.
- prop `solidOrientation`: SweepSolidOrientationTypes (rw) — Gets and sets the sweep solid orientation.
- prop `solidAlignedAxis`: Base (rw) — Gets and sets the axis to align the solid being swept with.
- prop `solidTwistAxis`: Base (rw) — Gets and sets the twist axis of the solid being swept.

### SymmetricExtentDefinition (ExtentDefinition)
A definition object that is used to define the extents of a feature to be symmetric.
- `create(distance: ValueInput, isFullLength: bool) -> SymmetricExtentDefinition` — Statically creates a new SymmetricExtentDefinition object.
    - `distance`: An input ValueInput objects that defines either half the extent of the extrude or the full extent, depending on the value of the isFullLength argument.
    - `isFullLength`: An input boolean that specifies if the distance specified defines the full or half length of the extrusion.
- prop `isFullLength`: bool (rw) — Gets and sets if the distance defines the full extent length or half the length.
- prop `distance`: Base (ro) — Returns the current extent distance.
- prop `taperAngle`: Base (ro) — Returns the current taper angle.

### ThickenFeature (Feature)
Object that represents an existing Thicken feature in a design.
- `setInputEntities(inputFaces: ObjectCollection, isChainSelection: bool = True) -> bool` — Sets the faces and patch bodies to thicken.
    - `inputFaces`: The faces or patch bodies to thicken.
    - `isChainSelection`: A boolean value for setting whether or not faces that are tangentially connected to the input faces (if any) will be included in the offset.
- `createForAssemblyContext(occurrence: Occurrence) -> ThickenFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `inputFaces`: ObjectCollection (rw) — Gets and sets the ObjectCollection containing the face and/or patch bodies to thicken.
- prop `thickness`: ModelParameter (ro) — Returns the parameter controlling the thickness.
- prop `isSymmetric`: bool (rw) — Gets and sets whether to add thickness symmetrically or only on one side of the face/s to thicken.
- prop `operation`: FeatureOperations (rw) — Gets and sets the feature operation to perform.
- prop `isChainSelection`: bool (ro) — Get and sets whether faces that are tangentially connected to the input faces will be included in the thicken feature.
- prop `nativeObject`: ThickenFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `thickenType`: ThickenTypes (rw) — Gets and sets the thicken type for the thicken.

### ThreadFeature (Feature)
Object that represents an existing thread feature in a design.
- `setThreadOffsetLength(threadOffset: ValueInput, threadLength: ValueInput, threadLocation: ThreadLocations) -> bool` — Sets the thread offset, length and location.
    - `threadOffset`: A ValueInput object that defines the thread offset.
    - `threadLength`: A ValueInput object that defines the thread length.
    - `threadLocation`: Indicates where the thread length is measured from.
- `createForAssemblyContext(occurrence: Occurrence) -> ThreadFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `inputCylindricalFace`: BRepFace (rw) — Gets and sets the threaded face.
- prop `isModeled`: bool (rw) — Gets and sets if the thread is physical or cosmetic thread.
- prop `isFullLength`: bool (rw) — Gets and sets if this thread is the full length of the cylinder.
- prop `threadLength`: ModelParameter (ro) — Gets the parameter that controls the depth of the thread.
- prop `threadOffset`: ModelParameter (ro) — Gets the parameter that controls the offset value of the thread.
- prop `threadLocation`: ThreadLocations (rw) — Gets and sets where the thread length is measured from.
- prop `threadInfo`: ThreadInfo (rw) — Gets and sets the thread data.
- prop `isRightHanded`: bool (rw) — Gets and sets if the thread is right or left-handed thread.
- prop `nativeObject`: ThreadFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `inputCylindricalFaces`: ObjectCollection (rw) — Gets and sets the cylindrical input faces.
- prop `hole`: HoleFeature (ro) — If this thread feature is was created as the result of creating a tapped hole, this property will return the associated hole feature.

### ThroughAllExtentDefinition (ExtentDefinition)
A definition object that is used to define the extents of a feature to be through all.
- `create() -> ThroughAllExtentDefinition` — Statically creates a new ThroughAllExtentDefinition object.
- prop `isPositiveDirection`: bool (rw) — Gets and sets if the direction is positive or negative.

### TimelineBuilderJob (core.Job)
A job that builds a parametric timeline from an input BRep body using the Timeline Builder cloud service.
- `createTimeline(body: BRepBody) -> TimelineBuilderJob` — Creates and starts a new TimelineBuilderJob from the given BRep body.
    - `body`: The BRepBody to use as input.
- prop `resultDocument`: Document (ro) — Returns the document created by a successfully completed job, or null if the job has not produced a document yet (i.e.

### TimelineGroup (TimelineObject)
Represents a group in the timeline.
- `deleteMe(deleteGroupAndContents: bool) -> bool` — Deletes the group with the option of deleting or keeping the contents.
    - `deleteGroupAndContents`: Indicates if the group and its contents should be deleted or if only the group should be deleted and the contents kept and expanded.
- `item(index: int) -> TimelineObject` — Function that returns the specified timeline object within the group using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `isCollapsed`: bool (rw) — Indicates if the group is collapsed or expanded.
- prop `count`: int (ro) — The number of items in the group.

### ToEntityExtentDefinition (ExtentDefinition)
A definition object that is used to define the extents of a feature to be up to a specified construction plane or face.
- `create(entity: Base, isChained: bool, offset: ValueInput = None) -> ToEntityExtentDefinition` — Statically creates a new ToEntityExtentDefinition object.
    - `entity`: The construction plane or face that the feature extent it up to.
    - `isChained`: 
    - `offset`: A optional input value that defines an offset distance of the entity that will be used for the extent.
- prop `entity`: Base (rw) — Gets and sets the entity that the feature extent is defined up to.
- prop `offset`: Base (ro) — Returns the current offset.
- prop `isChained`: bool (rw) — Gets and sets whether connected faces to the input entity should also be used when calculating the extent or if the input entity should be extended.
- prop `directionHint`: Vector3D (rw) — Gets and sets a direction that is used when the result is ambiguous.
- prop `isMinimumSolution`: bool (rw) — Gets and sets if the minimum or maximum solution is calculated.

### TrimFeature (Feature)
Object that represents an existing trim feature in a design.
- `createForAssemblyContext(occurrence: Occurrence) -> TrimFeature` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `applyCellChanges() -> bool` — After making any changes to the set of selected cells you must call this method to indicate all changes have been made and to apply those changes to the feature.
- prop `trimTool`: Base (rw) — Gets and sets the entity (a patch body, B-Rep face, construction plane or sketch curve) that intersects the trim tool.
- prop `bRepCells`: BRepCells (ro) — Gets the set of valid cells that have been calculated based on the current inputs.
- prop `nativeObject`: TrimFeature (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### TwoDistancesChamferEdgeSet (ChamferEdgeSet)
Provides access to the edges and the parameters associated with a two distances chamfer.
- prop `edges`: ObjectCollection (rw) — Gets and sets the edges that will be chamfered.
- prop `distanceOne`: ModelParameter (ro) — Returns the model parameter that controls the first offset distance of the chamfer.
- prop `distanceTwo`: ModelParameter (ro) — Returns the model parameter that controls the first offset distance of the chamfer.
- prop `isFlipped`: bool (rw) — Gets and sets if the chamfer is flipped.

### TwoSidesAngleExtentDefinition (ExtentDefinition)
Defines the inputs for a TwoSidesAngleExtentDefinition object.
- prop `angleOne`: ModelParameter (ro) — Gets the ModelParameter that defines the angle on the first side.
- prop `angleTwo`: ModelParameter (ro) — Gets the ModelParameter that defines the angle on the second side.

### UserParameter (Parameter)
Represents a User Parameter.
- `deleteMe() -> bool` — Deletes the user parameter A parameter can only be deleted if it is a UserParameter and it is not referenced by other parameters.
- prop `userParameters`: UserParameters (ro) — Returns the Collection containing the UserParameter.
- prop `design`: Design (ro) — Returns the Design containing the UserParameter.

### VariableRadiusFilletEdgeSet (FilletEdgeSet)
Provides access to the edges and the parameters associated with a variable radius fillet.
- `addMidPosition(position: ValueInput, radius: ValueInput) -> bool` — Creates a new mid position radius on the variable radius edge set.
    - `position`: The position where the new radius is to be created.
    - `radius`: A ValueInput object that defines the radius at the defined position.
- `deleteMidPosition(positionIndex: int) -> bool` — Deletes the specified mid position from the variable radius fillet.
    - `positionIndex`: The index of the mid position to delete.
- prop `edges`: ObjectCollection (rw) — Gets and sets an ObjectCollection containing the edges that are filleted.
- prop `startRadius`: ModelParameter (ro) — Returns the model parameter that controls the start radius of the fillet.
- prop `endRadius`: ModelParameter (ro) — Returns the model parameter that controls the end radius of the fillet.
- prop `midRadii`: ParameterList (ro) — Returns a list of model parameters that control radius of the fillet at each position defined along the edge set.
- prop `midPositions`: ParameterList (ro) — Returns a list of model parameters that control the location of each mid point radius.

### VariableRadiusFilletEdgeSetInput (FilletEdgeSetInput)
Provides access to the edges and the parameters associated with a variable radius fillet.
- `setMidRadii(radii: list[ValueInput], positions: list[ValueInput]) -> bool` — Defines any additional points along the fillet where a radius is specified.
    - `radii`: An array of ValueInput objects that define the radii at positions along the edge(s).
    - `positions`: An array of ValueInput objects that defines the positions of any additional radii along the edge(s).
- prop `startRadius`: ValueInput (rw) — Gets and sets a ValueInput object that defines the starting radius of the fillet.
- prop `endRadius`: ValueInput (rw) — Gets and sets a ValueInput object that defines the ending radius of the fillet.

### WebFeature (Feature)
Object that represents an existing web feature in a design.

### WebLightDistribution (LightDistribution)
** This class is a preview feature and may change in future releases.
- prop `iesProfileData`: str (rw) — Gets and sets the IES photometric profile of this distribution.
