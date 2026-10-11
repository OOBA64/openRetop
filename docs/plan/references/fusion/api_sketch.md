# Fusion API digest: sketch

Generated from Fusion's shipped Python API stubs (`API/Python/packages/adsk/defs/adsk/fusion.py`), condensed to signatures, enum values and a one-line summary each. Units in the API are **cm** and **radians**. See [FUSION_REFERENCE.md](../FUSION_REFERENCE.md).

### DimensionOrientations
The different dimension orientations.
Values: AlignedDimensionOrientation=0, HorizontalDimensionOrientation=1, VerticalDimensionOrientation=2

### SketchCurveConstructionStates
Used by the Sketch.setConstructionState method setting the construction state on sketch curves.
Values: ToggleSketchCurveConstructionState=0, ConstructionSketchCurveConstructionState=1, NormalSketchCurveConstructionState=2

### SketchLineCenterlineStates
Used by the Sketch.setCenterlineState method setting the centerline state on sketch lines.
Values: ToggleSketchLineCenterlineState=0, CenterlineSketchLineCenterlineState=1, NormalSketchLineCenterlineState=2

### TextBoxKeyPoints
Defines the nine key points that exist for a sketch text box and can be used as the origin when rotating the text.
Values: TopLeftTextBoxKeyPoint=0, TopMiddleTextBoxKeyPoint=1, TopRightTextBoxKeyPoint=2, MiddleLeftTextBoxKeyPoint=3, MiddleTextBoxKeyPoint=4, MiddleRightTextBoxKeyPoint=5, BottomLeftTextBoxKeyPoint=6, BottomMiddleTextBoxKeyPoint=7, BottomRightTextBoxKeyPoint=8

### AssemblyConstraint
Represents an assembly constraint.
- `deleteMe() -> bool` — Deletes this assembly constraint.
- `createForAssemblyContext(occurrence: Occurrence) -> AssemblyConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `name`: str (rw) — Gets and sets the name of the assembly constraint.
- prop `geometricRelationships`: GeometricRelationships (ro) — Returns the set of geometric relationships used for this assembly constraint.
- prop `parentComponent`: Component (ro) — Returns the parent component that owns this assembly constraint.
- prop `timelineObject`: TimelineObject (ro) — Returns the timeline object associated with this assembly constraint.
- prop `nativeObject`: AssemblyConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `isSuppressed`: bool (rw) — Gets and sets if this assembly constraint is suppressed.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this assembly constraint.
- prop `healthState`: FeatureHealthStates (ro) — Returns the current health state of the assembly constraint.
- prop `errorOrWarningMessage`: str (ro) — Returns the error or warning message in the case where the healthState property returns either WarningFeatureHealthState or ErrorFeatureHealthState.
- prop `entityToken`: str (ro) — Returns a token for the assembly constraint object.
- prop `isLightBulbOn`: bool (rw) — Gets and sets if the light bulb of this assembly constraint, as displayed in the browser, is on or off.
- prop `isVisible`: bool (ro) — Gets whether the assembly constraint is visible.

### AssemblyConstraintInput
Defines all of the information required to create a new assembly constraint.
- prop `geometricRelationships`: GeometricRelationships (ro) — Returns the collection object used to define the geometric relationships that the constraints will be inferred from.

### CircularPatternConstraintInput
This class defines the methods and properties that pertain to the definition of a circular pattern in a sketch.
- prop `entities`: list[SketchEntity] (rw) — Gets and sets the entities to pattern.
- prop `centerPoint`: SketchPoint (rw) — Gets and sets the sketch point that defines the center of the pattern.
- prop `quantity`: ValueInput (rw) — Gets and sets quantity of the elements.
- prop `totalAngle`: ValueInput (rw) — Gets and sets total angle.
- prop `isSymmetric`: bool (rw) — Gets and sets if the angle extent is in one direction or is symmetric.
- prop `isSuppressed`: list[bool] (rw) — Specifies which, if any, instances of the pattern are suppressed.

### GeometricConstraint
The base class for all geometric constraints.
- `deleteMe() -> bool` — Deletes this constraint.
- prop `isDeletable`: bool (ro) — Indicates if this constraint is deletable.
- prop `parentSketch`: Sketch (ro) — Returns the parent sketch object.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this geometric constraint.
- prop `entityToken`: str (ro) — Returns a token for the GeometricConstraint object.

### GeometricConstraints
A collection of all of the geometric constraints in a sketch.
- `item(index: int) -> GeometricConstraint` — Function that returns the specified sketch constraint using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addCoincident(point: SketchPoint, entity: SketchEntity) -> CoincidentConstraint` — Creates a new coincident constraint between two entities.
    - `point`: The SketchPoint that will be made coincident.
    - `entity`: The SketchPoint or sketch curve that the point will be made coincident to.
- `addCollinear(lineOne: SketchLine, lineTwo: SketchLine) -> CollinearConstraint` — Creates a new collinear constraint between two lines.
    - `lineOne`: The first line to create the constraint on.
    - `lineTwo`: The second line to create the constraint on.
- `addConcentric(entityOne: SketchCurve, entityTwo: SketchCurve) -> ConcentricConstraint` — Creates a new concentric constraint between two circles, arcs, ellipses, or elliptical arcs.
    - `entityOne`: The first circle, arc, ellipse or elliptical arc.
    - `entityTwo`: The second circle, arc, ellipse or elliptical arc.
- `addMidPoint(point: SketchPoint, midPointCurve: SketchCurve) -> MidPointConstraint` — Creates a new midpoint constraint between a point and a curve.
    - `point`: The point to constrain to the midpoint of a curve.
    - `midPointCurve`: The curve that defines the midpoint to constraint to.
- `addParallel(lineOne: SketchLine, lineTwo: SketchLine) -> ParallelConstraint` — Creates a new parallel constraint between two lines.
    - `lineOne`: The first SketchLine.
    - `lineTwo`: The second SketchLine.
- `addHorizontal(line: SketchLine) -> HorizontalConstraint` — Creates a new horizontal constraint on a line.
    - `line`: The line to constrain horizontally.
- `addHorizontalPoints(pointOne: SketchPoint, pointTwo: SketchPoint) -> HorizontalPointsConstraint` — Creates a new horizontal constraint between two points.
    - `pointOne`: The first SketchPoint to constrain horizontally.
    - `pointTwo`: The second SketchPoint to constrain horizontally.
- `addVertical(line: SketchLine) -> VerticalConstraint` — Creates a new vertical constraint on a line.
    - `line`: The line to constrain vertically.
- `addVerticalPoints(pointOne: SketchPoint, pointTwo: SketchPoint) -> VerticalPointsConstraint` — Creates a new vertical constraint between two points.
    - `pointOne`: The first SketchPoint to constrain vertically.
    - `pointTwo`: The second SketchPoint to constrain vertically.
- `addTangent(curveOne: SketchCurve, curveTwo: SketchCurve) -> TangentConstraint` — Creates a new tangent constraint between two curves.
    - `curveOne`: The first curve to be tangent.
    - `curveTwo`: The second curve to be tangent.
- `addSmooth(curveOne: SketchCurve, curveTwo: SketchCurve) -> SmoothConstraint` — Creates a new smooth constraint between two curves.
    - `curveOne`: The first curve to be constrained to be smooth to the second curve.
    - `curveTwo`: The second curve to be constrained to be smooth to the first curve.
- `addEqual(curveOne: SketchCurve, curveTwo: SketchCurve) -> EqualConstraint` — Creates a new equal constraint between two lines, or between arcs and circles.
    - `curveOne`: The first line, arc, or circle.
    - `curveTwo`: The second line, arc, or circle.
- `addSymmetry(entityOne: SketchEntity, entityTwo: SketchEntity, symmetryLine: SketchLine) -> SymmetryConstraint` — Creates a new symmetry constraint.
    - `entityOne`: The first sketch entity to be symmetric.
    - `entityTwo`: The second sketch entity to be symmetric.
    - `symmetryLine`: The SketchLine that defines the axis of symmetry.
- `createRectangularPatternInput(entities: list[SketchEntity], distanceType: PatternDistanceType) -> RectangularPatternConstraintInput` — Creates a new RectangularPatternConstraintInput object.
    - `entities`: An array of sketch entities to pattern.
    - `distanceType`: Specifies if the distances defined for the pattern define the overall size of the pattern or the distance between the rows and columns.
- `addRectangularPattern(input: RectangularPatternConstraintInput) -> RectangularPatternConstraint` — Creates a new rectangular pattern in the sketch.
    - `input`: A RectangularPatternConstraintInput object that defines all of inputs required to create the desired rectangular pattern.
- `createCircularPatternInput(inputEntities: list[SketchEntity], centerPoint: SketchPoint) -> CircularPatternConstraintInput` — Creates a CircularPatternConstraintInput object.
    - `inputEntities`: An array of sketch entities to be patterned.
    - `centerPoint`: A SketchPoint from the same sketch that defines the center of the pattern.
- `addCircularPattern(input: CircularPatternConstraintInput) -> CircularPatternConstraint` — Creates a new circular pattern in the sketch.
    - `input`: A CircularPatternConstraintInput object that defines the desired circular pattern.
- `addCoincidentToSurface(point: SketchPoint, surface: Base) -> CoincidentToSurfaceConstraint` — Creates a new coincident constraint between the sketch point and surface.
    - `point`: The SketchPoint to constrain to the surface.
    - `surface`: The BRepFace or ConstructionPlane the point will be coincident to.
- `addLineParallelToPlanarSurface(line: SketchLine, planarSurface: Base) -> LineParallelToPlanarSurfaceConstraint` — Creates a new parallel constraint between a sketch line and a planar surface that will constrain the line to lie on a plane parallel to the specified surface.
    - `line`: The SketchLine to constrain to the surface.
    - `planarSurface`: The planar BRepFace or CosntructionPlane the sketch line will be parallel to.
- `addLineOnPlanarSurface(line: SketchLine, planarSurface: Base) -> LineOnPlanarSurfaceConstraint` — Creates a new constraint that forces the sketch line to lie on a planar surface.
    - `line`: The SketchLine to constrain to the surface.
    - `planarSurface`: The planar BRepFace or CosntructionPlane the sketch line will lie on.
- `addPerpendicularToSurface(curve: SketchCurve, surface: Base) -> PerpendicularToSurfaceConstraint` — Creates a new perpendicular constraint that forces the sketch curve to be perpendicular to the specified surface.
    - `curve`: The SketchCurve to constrain to the surface.
    - `surface`: The BRepFace or ConstructionPlane the line will be perpendicular to.
- `createOffsetInput(curves: list[SketchCurve], offset: ValueInput) -> OffsetConstraintInput` — Creates an OffsetConstraintInput object.
    - `curves`: A set of end connected curves.
    - `offset`: The value that defines the offset.
- `addOffset2(input: OffsetConstraintInput) -> OffsetConstraint` — Creates an offset constraint, which results in creating a new set of curves that are an offset of the input curves.
    - `input`: The OffsetConstraintInput object that defines the offset to create.
- `addTwoSidesOffset(input: OffsetConstraintInput, linkOffsets: bool) -> list[OffsetConstraint]` — Creates two offset constraints, which results in creating two new sets of curves that are an offset of the input curves on each side of the original set of curves.
    - `input`: The OffsetConstraintInput object that defines the offset to create.
    - `linkOffsets`: Defines if the parameter driving the offset of the second side should reference the parameter of the first side.
- `addPolygon(lines: list[SketchLine]) -> PolygonConstraint` — Creates a polygon constraint on existing lines in the sketch.
    - `lines`: An array of existing SketchLine objects in this sketch that define a valid polygon.
- `addPerpendicular2(line: SketchLine, curve: SketchCurve) -> PerpendicularConstraint` — Creates a new perpendicular constraint between a line and another curve.
    - `line`: The line to create the constraint on.
    - `curve`: The other curve to create the constraint on.
- prop `count`: int (ro) — Returns the number of constraints in the sketch.

### OffsetConstraintInput
Used to define the inputs needed to create an offset constraint.
- prop `curves`: list[SketchCurve] (rw) — Gets and sets an array of SketchCurve objects that defines the connected curves that will be offset.
- prop `offset`: ValueInput (rw) — Gets and sets the value that defines the offset.
- prop `dimensionPoint`: Point3D (rw) — A location on one of the curves where the offset dimension will be created.
- prop `isTopologyMatched`: bool (rw) — Specifies if the offset curves must match the topology of the original curves.

### PolygonMesh
The PolygonMesh represents a mesh that can contain any combination of polygons, quads, and triangles.
- `compareWith(otherMesh: PolygonMesh, transform: Matrix3D = None, transformOther: Matrix3D = None) -> list[float]` — ** This method is a preview feature and may change in future releases.
    - `otherMesh`: The other polygon mesh to compare against.
    - `transform`: An optional transformation matrix applied to this polygon mesh before comparison.
    - `transformOther`: An optional transformation matrix applied to the other polygon mesh before comparison.
- prop `nodeCount`: int (ro) — Returns the number of nodes in the mesh.
- prop `nodeCoordinatesAsDouble`: list[float] (ro) — Returns the node coordinates as an array of doubles where they are the x, y, z components of each coordinate.
- prop `nodeCoordinatesAsFloat`: list[float] (ro) — Returns the node coordinates as an array of floats where they are the x, y, z components of each coordinate.
- prop `nodeCoordinates`: list[Point3D] (ro) — Returns the node coordinates as an array of Point3D objects.
- prop `triangleCount`: int (ro) — Returns the number of triangles in the mesh.
- prop `quadCount`: int (ro) — Returns the number of quads in the mesh.
- prop `polygonCount`: int (ro) — Returns the number of polygons (more than 4 sides) in the mesh.
- prop `normalVectorsAsDouble`: list[float] (ro) — Returns the normal vectors as an array of doubles where they are the x, y, z components of each vector.
- prop `normalVectorsAsFloat`: list[float] (ro) — Returns the normal vectors as an array of floats.
- prop `normalVectors`: list[Vector3D] (ro) — Returns the normal vectors as an array of Vector3D objects.
- prop `triangleNodeIndices`: list[int] (ro) — Returns the index values that index into the NodeCoordinates and NormalVectors arrays to define the three coordinates of each triangle and the corresponding normal.
- prop `quadNodeIndices`: list[int] (ro) — Returns the index values that index into the NodeCoordinates and NormalVectors arrays to define the four coordinates of each quad and the corresponding normal.
- prop `polygonNodeIndices`: list[int] (ro) — Returns the index values that index into the NodeCoordinates and NormalVectors arrays to define the coordinates of each polygon and the corresponding normal.
- prop `nodeCountPerPolygon`: list[int] (ro) — Returns the number of nodes that define each polygon.
- prop `triangleFaceGroupTempIds`: list[int] (ro) — Returns the face groups tempId values for every triangle of the mesh.
- prop `wallThickness`: list[float] (ro) — Returns the wall thickness per node in cm.

### Profile
Represents a profile in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> Profile` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `areaProperties(accuracy: CalculationAccuracy = CalculationAccuracy.LowCalculationAccuracy) -> AreaProperties` — Calculates the area properties for the profile.
    - `accuracy`: Specifies the desired level of computational accuracy of the property calculations.
- prop `boundingBox`: BoundingBox3D (ro) — Returns the 3D bounding box of the profile in sketch space.
- prop `plane`: Plane (ro) — Returns the plane the profile is defined in.
- prop `profileLoops`: ProfileLoops (ro) — The loops or closed areas within this profile.
- prop `parentSketch`: Sketch (ro) — Returns the parent sketch of the profile.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `nativeObject`: Profile (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `entityToken`: str (ro) — Returns a token for the Profile object.
- prop `face`: BRepFace (ro) — Returns a temporary BRepFace object that is the same shape as the profile.
- prop `isOnSketchPlane`: bool (ro) — Indicates if the profile lies on the parent sketch plane.

### ProfileCurve
A single curve in a profile.
- `createForAssemblyContext(occurrence: Occurrence) -> ProfileCurve` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `geometry`: Curve3D (ro) — Returns the geometric entity of this portion of the profile.
- prop `geometryType`: Curve3DTypes (ro) — Return the geometry type that the Geometry property will return.
- prop `sketchEntity`: SketchEntity (ro) — Returns the associated sketch entity that defines this curve.
- prop `parentProfileLoop`: ProfileLoop (ro) — Returns the parent ProfileLoop object.
- prop `parentProfile`: Profile (ro) — Returns the parent Profile object.
- prop `parentSketch`: Sketch (ro) — Returns the parent Profile object.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `nativeObject`: ProfileCurve (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `boundingBox`: BoundingBox3D (ro) — Returns the bounding box of the profile curve in sketch space.

### ProfileCurves
A collection of profile curves within a profile loop.
- `item(index: int) -> ProfileCurve` — Function that returns the specified profile curve using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `count`: int (ro) — Returns the number of curves in the collection.

### ProfileLoop
A loop within a profile.
- `createForAssemblyContext(occurrence: Occurrence) -> ProfileLoop` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `isOuter`: bool (ro) — Indicates if this is an outer or inner loop.
- prop `profileCurves`: ProfileCurves (ro) — Returns a collection of the curves making up this loop.
- prop `parentProfile`: Profile (ro) — Returns the parent Profile object.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `nativeObject`: ProfileLoop (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### ProfileLoops
A collection of loops within a Profile.
- `item(index: int) -> ProfileLoop` — Function that returns the specified profile loop using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `count`: int (ro) — Returns the number of loops within this profile.

### Profiles
A collection of all of the closed profiles currently calculated for this sketch.
- `item(index: int) -> Profile` — Function that returns the specified closed profile using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `count`: int (ro) — Returns the number of closed profiles in the sketch.

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

### Sketch
Represents a sketch within a component.
- `projectCutEdges(body: BRepBody) -> ObjectCollection` — Intersects the specified body with the sketch plane and creates new curves representing the intersection.
    - `body`: The body to be intersected by the sketch.
- `include(entity: Base) -> ObjectCollection` — Creates new sketch curves and points that represent the specified entity as sketch geometry.
    - `entity`: The entity to include into the sketch.
- `findConnectedCurves(curve: SketchCurve) -> ObjectCollection` — Finds the sketch curves that are end connected to the input curve.
    - `curve`: The initial sketch curve that will be used to find the connected curves.
- `modelToSketchSpace(modelCoordinate: Point3D) -> Point3D` — A specified point in model space returns the equivalent point in sketch space.
    - `modelCoordinate`: A coordinate in model space.
- `sketchToModelSpace(sketchCoordinate: Point3D) -> Point3D` — A specified point in sketch space returns the equivalent point in model space.
    - `sketchCoordinate`: A coordinate in sketch space.
- `move(sketchEntities: ObjectCollection, transform: Matrix3D) -> bool` — Moves the specified sketch entities using the specified transform.
    - `sketchEntities`: A collection of sketch entities to transform.
    - `transform`: The transform that defines the move, rotate or scale.
- `copy(sketchEntities: ObjectCollection, transform: Matrix3D, targetSketch: Sketch = None) -> ObjectCollection` — Copies the specified sketch entities, applying the specified transform.
    - `sketchEntities`: The collection of sketch entities to copy.
    - `transform`: The transform to apply to the copied entities.
    - `targetSketch`: Optionally specifies the sketch to copy the entities to.
- `deleteMe() -> bool` — Deletes the sketch.
- `importSVG(fullFilename: str, xPosition: float, yPosition: float, scale: float) -> bool` — Imports the contents of an SVG file into the active sketch.
    - `fullFilename`: The full filename, including the path, of the SVG file.
    - `xPosition`: The X offset in centimeters in the sketch for the origin of the SVG data relative to the sketch origin.
    - `yPosition`: The Y offset in centimeters in the sketch for the origin of the SVG data relative to the sketch origin.
    - `scale`: The scale value to apply to the imported SVG data.
- `createForAssemblyContext(occurrence: Occurrence) -> Sketch` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `redefine(planarEntity: Base) -> bool` — Changes which plane the sketch is based on.
    - `planarEntity`: A construction plane or planar face that defines the sketch plane
- `intersectWithSketchPlane(entities: list[Base]) -> list[SketchEntity]` — Intersects the specified entities (BRepBody, BRepFace, BRepEdge, BRepVertex, SketchCurve, ConstructionPoint, ConstructionAxis, and ConstructionPlane) with the sketch plane and creates sketch geometry that represents the intersection.
    - `entities`: An array containing the entities to intersect with the sketch plane.
- `projectToSurface(faces: list[BRepFace], curves: list[Base], projectType: SurfaceProjectTypes, directionEntity: Base = None) -> list[SketchEntity]` — Projects the specified set of curves onto the specified set of faces using the specified method of projection.
    - `faces`: An array of BRepFace objects that the curves will be projected onto.
    - `curves`: An array of various curve objects that will be projected onto the faces.
    - `projectType`: Specifies which projection type to use which defines the direction of projection.
    - `directionEntity`: if the projectType argument is AlongVectorSurfaceProjectType, this argument must be specified and defines the direction of projection.
- `setConstructionState(sketchCurves: list[SketchCurve], constructionState: SketchCurveConstructionStates) -> bool` — Method that sets the Construction state for an array of sketch curves.
    - `sketchCurves`: An array of sketch curves to set the construction status.
    - `constructionState`: Input enum value that specifies if the construction state of the input curves should be toggled, set to construction, or set to normal.
- `setCenterlineState(sketchLines: list[SketchLine], centerlineState: SketchLineCenterlineStates) -> bool` — Method that sets the Centerline state for an array of sketch lines.
    - `sketchLines`: An array of sketch lines to set the centerline status
    - `centerlineState`: Input enum value that specifies if the centerline state of the input lines should be toggled, set to centerline, or set to normal
- `createSpunProfile(input: SpunProfileInput) -> list[SketchEntity]` — Creates sketch geometry that represents the spun profile.
    - `input`: The SpunProfileInput object that specifies the input needed to create the spun profile.
- `createSpunProfileInput(entities: list[Base], axis: Base) -> SpunProfileInput` — Creates a new SpunProfileInput object that is used to specify the input needed to create a spun profile.
    - `entities`: An array containing the entities (BRepBody or BRepFace) to create a spun profile.
    - `axis`: The axis can be a sketch line, construction axis, or linear edge.
- `addCenterToCenterSlot(startPoint: Base, endPoint: Base, width: ValueInput, createWidthDimension: bool = False, length: ValueInput = None, angle: ValueInput = None) -> list[Base]` — Creates the geometry that represents a slot.
    - `startPoint`: The start point of the slot.
    - `endPoint`: The end point of the slot.
    - `width`: A ValueInput object that defines the width of the slot.
    - `createWidthDimension`: Specifies if a dimension constraint and its associated parameter is created to control the width of the slot.
    - `length`: Optional argument that defines the length of the slot using a ValueInput.
    - `angle`: Optional argument that defines the angle of the slot using a ValueInput.
- `project2(entities: list[Base], isLinked: bool) -> list[SketchEntity]` — Projects the specified entity or entities onto the X-Y plane of the sketch and returns the created sketch entity(s).
    - `entities`: An array containing the entities to project.
    - `isLinked`: A Boolean that indicates if the resulting sketch curves will be parametrically linked to the source geometry that was projected.
- `addCenterPointSlot(centerPoint: Base, endPoint: Base, width: ValueInput, createWidthDimension: bool = False, halfLength: ValueInput = None, angle: ValueInput = None) -> list[Base]` — Creates the geometry that represents a slot where the first point defines the center of the slot and the second point defines the direction and half-length.
    - `centerPoint`: The center point of the slot.
    - `endPoint`: A point that defines the direction and half-length of the slot.
    - `width`: A ValueInput object that defines the width of the slot.
    - `createWidthDimension`: Specifies if a dimension constraint and its associated parameter is created to control the width of the slot.
    - `halfLength`: Optional argument that defines half the length of the slot using a ValueInput.
    - `angle`: Optional argument that defines the angle of the slot using a ValueInput.
- `addOverallSlot(startPoint: Base, endPoint: Base, width: ValueInput, createWidthDimension: bool = False, length: ValueInput = None, angle: ValueInput = None) -> list[Base]` — Creates the geometry that represents an overall slot.
    - `startPoint`: The start point of the slot.
    - `endPoint`: The end point of the slot.
    - `width`: A ValueInput object that defines the width of the slot.
    - `createWidthDimension`: Specifies if a dimension constraint and its associated parameter is created to control the width of the slot.
    - `length`: Optional argument that defines the overall length of the slot using a ValueInput.
    - `angle`: Optional argument that defines the angle of the slot using a ValueInput.
- `createAutoConstrainInput() -> AutoConstrainInput` — Creates a new AutoConstrainInput object associated with this sketch.
- `autoConstrain(input: AutoConstrainInput) -> AutoConstrainResult` — Auto constrains the sketch using the information provided by the input object.
    - `input`: The AutoConstrainInput object that defines the various settings to use when fully constraining the sketch.
- `mirror(sketchEntities: list[SketchEntity], mirrorLine: Base) -> list[SketchEntity]` — Mirrors the specified sketch entities about a mirror line and returns the newly created sketch entities (mirrored input entities together with the auxiliary sketch points - line endpoints, arc/ellipse centers, spline fit points, etc.
    - `sketchEntities`: The sketch entities to mirror.
    - `mirrorLine`: <p>The entity that defines the axis of symmetry.
- `addThreePointArcSlot(startPoint: Base, endPoint: Base, pointOnArc: Point3D, width: ValueInput, createWidthDimension: bool = False) -> list[Base]` — Creates the geometry that represents a three-point arc slot.
    - `startPoint`: The start point of the arc that defines the center line of the slot.
    - `endPoint`: The end point of the arc that defines the center line of the slot.
    - `pointOnArc`: A Point3D that lies on the arc and defines the arc's curvature.
    - `width`: A ValueInput object that defines the width of the slot.
    - `createWidthDimension`: Specifies if a dimension constraint and its associated parameter is created to control the width of the slot.
- `addCenterPointArcSlot(centerPoint: Base, startPoint: Base, endPoint: Base, width: ValueInput, radius: ValueInput = None, angle: ValueInput = None, createWidthDimension: bool = False, createRadiusDimension: bool = False, createAngleDimension: bool = False) -> list[Base]` — Creates the geometry that represents a center-point arc slot.
    - `centerPoint`: The center point of the center arc of the slot.
    - `startPoint`: The start point of the center arc of the slot.
    - `endPoint`: A point that defines the center of the end of the slot.
    - `width`: A ValueInput object that defines the width of the slot.
    - `radius`: An optional ValueInput object that defines the radius of the slot from the center to the end point (i.e.
    - `angle`: An optional ValueInput object that defines the angle of the slot as measured from a horizontal line.
    - `createWidthDimension`: Specifies if a dimension constraint and its associated parameter is created to control the width of the slot.
    - `createRadiusDimension`: Specifies if a dimension constraint and its associated parameter is created to control the radius of the slot.
    - `createAngleDimension`: Specifies if a dimension constraint and its associated parameter is created to control the angle of the slot.
- `scale(sketchEntities: list[SketchEntity], referencePoint: Point3D, scaleFactor: float) -> bool` — Scales the specified sketch entities about the specified reference point by the specified scale factor.
    - `sketchEntities`: An array of sketch entities to scale.
    - `referencePoint`: The reference point about which to scale.
    - `scaleFactor`: The uniform scale factor to apply.
- prop `name`: str (rw) — Gets and sets the name of this sketch as seen in the browser and timeline.
- prop `sketchPoints`: SketchPoints (ro) — Returns the sketch points collection associated with this sketch.
- prop `sketchCurves`: SketchCurves (ro) — Returns the sketch curves collection associated with this sketch.
- prop `sketchDimensions`: SketchDimensions (ro) — Returns the sketch dimensions collection associated with this sketch.
- prop `geometricConstraints`: GeometricConstraints (ro) — Returns the sketch constraints collection associated with this sketch.
- prop `transform`: Matrix3D (rw) — Gets and sets the transform of the sketch with respect to model space.
- prop `isParametric`: bool (ro) — Indicates if this sketch is parametric or not.
- prop `isVisible`: bool (rw) — Gets if this sketch is currently visible in the graphics window.
- prop `areDimensionsShown`: bool (rw) — Indicates if the dimensions of the sketch are displayed when the sketch is not active (in sketch edit mode)
- prop `areProfilesShown`: bool (rw) — Indicates if the profiles of the sketch are displayed
- prop `origin`: Point3D (ro) — Returns the origin point of the sketch in model space.
- prop `xDirection`: Vector3D (ro) — Returns the X direction of the sketch as defined in model space.
- prop `yDirection`: Vector3D (ro) — Returns the Y direction of the sketch as defined in model space.
- prop `referencePlane`: Base (rw) — Gets and sets the construction plane or planar face the sketch is associated to.
- prop `isComputeDeferred`: bool (rw) — This property temporarily turns off sketch computing.
- prop `profiles`: Profiles (ro) — Returns the profiles currently computed for the sketch.
- prop `timelineObject`: TimelineObject (ro) — Returns the timeline object associated with this sketch.
- prop `parentComponent`: Component (ro) — Returns the parent Component.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `nativeObject`: Sketch (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `boundingBox`: BoundingBox3D (ro) — Returns the 3D bounding box of the sketch
- prop `sketchTexts`: SketchTexts (ro) — Returns the sketch text collection associated with this sketch.
- prop `originPoint`: SketchPoint (ro) — Returns the sketch point that was automatically created by projecting the origin construction point into the sketch.
- prop `isFullyConstrained`: bool (ro) — Indicates if this sketch is fully constrained.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this sketch.
- prop `baseOrFormFeature`: Base (ro) — This property returns the base or form feature that this sketch is associated with.
- prop `healthState`: FeatureHealthStates (ro) — Returns the current health state of this sketch.
- prop `errorOrWarningMessage`: str (ro) — Returns the error or warning message in the case where the healthState property returns either WarningFeatureHealthState or ErrorFeatureHealthState.
- prop `revisionId`: str (ro) — Returns the current revision ID of the sketch.
- prop `areConstraintsShown`: bool (rw) — Indicates if the constraints of the sketch are displayed when the sketch is active.
- prop `arePointsShown`: bool (rw) — Indicates if the sketch points in the sketch are displayed.
- prop `isLightBulbOn`: bool (rw) — Gets and set if the light bulb beside the sketch node in the browser is on or not.
- prop `entityToken`: str (ro) — Returns a token for the Sketch object.
- prop `isModelSliced`: bool (rw) — Gets and sets whether the model is sliced along the sketch plane when this sketch is active.
- prop `isProjectedGeometryShown`: bool (rw) — Gets and sets whether projected geometry in the sketch is displayed.
- prop `isConstructionGeometryShown`: bool (rw) — Gets and sets whether construction geometry in the sketch is displayed.
- prop `isDerived`: bool (ro) — Returns if this sketch is derived from another design.
- prop `deriveFeature`: DeriveFeature (ro) — Returns the DeriveFeature if this sketch is derived from another design.

### SketchArcs
The collection of arcs in a sketch.
- `item(index: int) -> SketchArc` — Function that returns the specified sketch arc using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addByCenterStartSweep(centerPoint: Base, startPoint: Base, sweepAngle: float) -> SketchArc` — Creates a sketch arc that is always parallel to the x-y plane of the sketch and is centered at the specified point.
    - `centerPoint`: The center point of the arc.
    - `startPoint`: The start point of the arc.
    - `sweepAngle`: The sweep of the arc.
- `addByThreePoints(startPoint: Base, point: Point3D, endPoint: Base) -> SketchArc` — Creates a sketch arc that passes through the three points.
    - `startPoint`: The start point of the arc.
    - `point`: A point along the arc.
    - `endPoint`: The end point of the arc.
- `addFillet(firstEntity: SketchCurve, firstEntityPoint: Point3D, secondEnitity: SketchCurve, secondEntityPoint: Point3D, radius: float) -> SketchArc` — Creates a fillet between two sketch entities The side (quadrant) the fillet is created on is determined by the points specified.
    - `firstEntity`: The first curve for the fillet definition.
    - `firstEntityPoint`: A point on or closer to one end of the first curve that indicates the side to create the fillet on
    - `secondEnitity`: The second curve for the fillet definition.
    - `secondEntityPoint`: A point on or closer to one end of the second curve that indicates the side to create the fillet on
    - `radius`: radius of the arc in centimeters
- `addByCenterStartEnd(centerPoint: Base, startPoint: Base, endPoint: Base, normal: Vector3D = None) -> SketchArc` — Creates a sketch arc that is centered at the specified point and between the two input points.
    - `centerPoint`: The center point of the arc.
    - `startPoint`: The start point of the arc.
    - `endPoint`: The end point of the arc.
    - `normal`: An optional argument that specifies the normal of the plane the arc will be created on.
- prop `count`: int (ro) — Returns the number of arcs in the sketch.

### SketchCircles
The collection of circles in a sketch.
- `item(index: int) -> SketchCircle` — Function that returns the specified sketch circle using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addByCenterRadius(centerPoint: Base, radius: float) -> SketchCircle` — Creates a sketch circle that is always parallel to the x-y plane of the sketch and is centered at the specified point.
    - `centerPoint`: The center point of the circle.
    - `radius`: The radius of the circle in centimeters.
- `addByTwoPoints(pointOne: Point3D, pointTwo: Point3D) -> SketchCircle` — Creates a sketch circle where the circle passes through the two points and the distance between the two points is the diameter of the circle.
    - `pointOne`: A Point3D object that defines a point is sketch space and lies on the x-y plane of the sketch.
    - `pointTwo`: A Point3D object that defines a point is sketch space and lies on the x-y plane of the sketch.
- `addByThreePoints(pointOne: Point3D, pointTwo: Point3D, pointThree: Point3D) -> SketchCircle` — Creates a sketch circle that passes through the three points.
    - `pointOne`: The first point that the circle will pass through.
    - `pointTwo`: The second point that the circle will pass through.
    - `pointThree`: The third point that the circle will pass through.
- `addByTwoTangents(tangentOne: SketchLine, tangentTwo: SketchLine, radius: float, hintPoint: Point3D) -> SketchCircle` — Creates a sketch circle that is tangent to the two input lines.
    - `tangentOne`: The first line that the circle will be tangent to.
    - `tangentTwo`: The second line that the circle will be tangent to.
    - `radius`: The radius of the circle in centimeters.
    - `hintPoint`: A point that specifies which of the possible four solutions to use when creating the circle.
- `addByThreeTangents(tangentOne: SketchLine, tangentTwo: SketchLine, tangentThree: SketchLine, hintPoint: Point3D) -> SketchCircle` — Creates a sketch circle that is tangent to the three input lines.
    - `tangentOne`: The first line that the circle will be tangent to.
    - `tangentTwo`: The second line that the circle will be tangent to.
    - `tangentThree`: The third line that the circle will be tangent to.
    - `hintPoint`: A point that specifies which of the possible multiple solutions to use when creating the circle.
- prop `count`: int (ro) — Returns the number of circles in the sketch.

### SketchConicCurves
The collection of conic curves in a sketch.
- `item(index: int) -> SketchConicCurve` — Function that returns the specified conic curve using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(startPoint: Base, endPoint: Base, apexPoint: Base, rhoValue: float) -> SketchConicCurve` — Creates a new conic curve.
    - `startPoint`: The start point of the conic curve.
    - `endPoint`: The end point of the conic curve.
    - `apexPoint`: The apex point of the conic curve.
    - `rhoValue`: Double that specifies the rho value for the conic.
- prop `count`: int (ro) — Returns the number of conic curves in the sketch.

### SketchControlPointSplines
The collection of control point splines in a sketch.
- `item(index: int) -> SketchControlPointSpline` — Function that returns the specified sketch control point spline using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(controlPoints: list[Base], degree: SplineDegrees) -> SketchControlPointSpline` — Creates a new control point spline.
    - `controlPoints`: An array of points that define the control points of the curve's polygon.
    - `degree`: Specifies the degree of the spline.
- prop `count`: int (ro) — Returns the number of control point splines in the sketch.

### SketchCurves
A collection of sketch curves in a sketch.
- `item(index: int) -> SketchCurve` — Function that returns the specified sketch curve using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `count`: int (ro) — Returns the number of sketch curves in the sketch.
- prop `sketchArcs`: SketchArcs (ro) — Returns the sketch arcs collection associated with this sketch.
- prop `sketchCircles`: SketchCircles (ro) — Returns the sketch circles collection associated with this sketch.
- prop `sketchEllipses`: SketchEllipses (ro) — Returns the sketch ellipses collection associated with this sketch.
- prop `sketchEllipticalArcs`: SketchEllipticalArcs (ro) — Returns the sketch elliptical arcs collection associated with this sketch.
- prop `sketchLines`: SketchLines (ro) — Returns the sketch lines collection associated with this sketch.
- prop `sketchFittedSplines`: SketchFittedSplines (ro) — Returns the sketch splines collection associated with this sketch.
- prop `sketchFixedSplines`: SketchFixedSplines (ro) — Returns the fixed sketch splines collection associated with this sketch.
- prop `sketchConicCurves`: SketchConicCurves (ro) — Returns the conic curves collection associated with this sketch.
- prop `sketchControlPointSplines`: SketchControlPointSplines (ro) — Returns the control point splines collection associated with this sketch.
- prop `sketchIsoparametricCurves`: SketchIsoparametricCurves (ro) — Returns the isoparametric curves collection associated with this sketch.

### SketchDimension
The base class for the all sketch dimensions.
- `deleteMe() -> bool` — Deletes this dimension.
- prop `isDeletable`: bool (ro) — Indicates if this dimension is deletable.
- prop `textPosition`: Point3D (rw) — Gets and sets position of the dimension text.
- prop `parentSketch`: Sketch (ro) — Returns the parent sketch object.
- prop `parameter`: ModelParameter (ro) — Returns the associated parameter or null if there is no associated parameter.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `isDriving`: bool (rw) — Gets and sets if the dimension is Driving or is Driven.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this sketch dimension.
- prop `entityToken`: str (ro) — Returns a token for the SketchDimension object.
- prop `value`: float (rw) — Gets and sets the current value of the sketch dimension.

### SketchDimensionList
A list of sketch dimensions.
- `item(index: int) -> SketchDimension` — Function that returns the specified sketch dimension using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `count`: int (ro) — Returns the number of sketch dimensions in the sketch.

### SketchDimensions
A collection of the dimensions in a sketch.
- `item(index: int) -> SketchDimension` — Function that returns the specified sketch dimension using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addDistanceDimension(pointOne: SketchPoint, pointTwo: SketchPoint, orientation: DimensionOrientations, textPoint: Point3D, isDriving: bool = True) -> SketchLinearDimension` — Creates a new linear dimension constraint between the two input entities.
    - `pointOne`: The first SketchPoint to dimension to.
    - `pointTwo`: The second SketchPoint to dimension to..
    - `orientation`: The orientation of the dimension.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addOffsetDimension(line: SketchLine, entityTwo: SketchEntity, textPoint: Point3D, isDriving: bool = True) -> SketchOffsetDimension` — Creates a new linear dimension constraint between the two input entities.
    - `line`: The SketchLine to dimension to.
    - `entityTwo`: The parallel SketchLine or SketchPoint to dimension to.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addAngularDimension(lineOne: SketchLine, lineTwo: SketchLine, textPoint: Point3D, isDriving: bool = True) -> SketchAngularDimension` — Creates a new angular dimension constraint between the two input lines.
    - `lineOne`: The first SketchLine to dimension to.
    - `lineTwo`: The second SketchLine to dimension to.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addDiameterDimension(entity: SketchCurve, textPoint: Point3D, isDriving: bool = True) -> SketchDiameterDimension` — Creates a new diameter dimension constraint on the arc or circle.
    - `entity`: The SketchCircle or SketchArc to dimension.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addRadialDimension(entity: SketchCurve, textPoint: Point3D, isDriving: bool = True) -> SketchRadialDimension` — Creates a new radial dimension constraint on the arc or circle.
    - `entity`: The SketchCircle or SketchArc to dimension.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addEllipseMajorRadiusDimension(ellipse: SketchCurve, textPoint: Point3D, isDriving: bool = True) -> SketchEllipseMajorRadiusDimension` — Creates a new dimension constraint on the major radius of an ellipse.
    - `ellipse`: The SketchEllipse to dimension.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addEllipseMinorRadiusDimension(ellipse: SketchCurve, textPoint: Point3D, isDriving: bool = True) -> SketchEllipseMinorRadiusDimension` — Creates a new dimension constraint on the minor radius of an ellipse.
    - `ellipse`: The SketchEllipse to dimension.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addConcentricCircleDimension(circleOne: SketchCurve, circleTwo: SketchCurve, textPoint: Point3D, isDriving: bool = True) -> SketchConcentricCircleDimension` — Creates a new dimension constraint between to concentric circles or arcs.
    - `circleOne`: The first SketchCircle or SketchArc to dimension.
    - `circleTwo`: The second SketchCircle or SketchArc to dimension.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addTangentDistanceDimension(entityOne: SketchEntity, isCloseToEnityTwo: bool, entityTwo: SketchCurve, isCloseToEnityOne: bool, textPoint: Point3D, isDriving: bool = True) -> SketchTangentDistanceDimension` — Creates a new linear dimension from between a line and circle or arc and a second circle or arc where the dimension is to the tangent on the edge of the circle or arc.
    - `entityOne`: The first entity to dimension to.
    - `isCloseToEnityTwo`: If entityOne is a circle or arc this specifies which side of the circle or arc the dimension will be tangent to.
    - `entityTwo`: A SketchCircle or SketchArc entity that you will dimension to.
    - `isCloseToEnityOne`: Specifies which side of the circle or arc input as the entityTwo argument the dimension will be tangent to.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addLinearDiameterDimension(centerLine: SketchLine, entityTwo: SketchEntity, textPoint: Point3D, isDriving: bool = True) -> SketchLinearDiameterDimension` — Creates a new linear dimension showing the diameter where the first line acts as the center line and the second entity defines the size.
    - `centerLine`: The SketchLine to dimension to which acts as the center line.
    - `entityTwo`: The parallel SketchLine or SketchPoint to dimension to.
    - `textPoint`: A Point3D object that defines the position of the dimension text.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addDistanceBetweenPointAndSurfaceDimension(point: SketchPoint, surface: Base, isDriving: bool = True) -> SketchDistanceBetweenPointAndSurfaceDimension` — Creates a new linear dimension controlling the distance between a sketch point and the specified surface or point.
    - `point`: The SketchPoint being constrained by the dimension.
    - `surface`: The BRepFace or ConstructionPlane to which the dimension will anchor.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- `addDistanceBetweenLineAndPlanarSurfaceDimension(line: SketchLine, planarSurface: Base, isDriving: bool = True) -> SketchDistanceBetweenLineAndPlanarSurfaceDimension` — Creates a new linear dimension controlling the distance between a sketch line and the specified planar face or construction plane.
    - `line`: The SketchLine being constrained by the dimension.
    - `planarSurface`: The planar BRepFace or ConstructionPlane that the dimension will anchor to.
    - `isDriving`: Optional argument that specifies if a driving (the dimension controls the geometry) or a driven (the geometry controls the dimension) dimension is created.
- prop `count`: int (ro) — Returns the number of sketch dimensions in the sketch.

### SketchEllipses
The collection of ellipses in a sketch.
- `item(index: int) -> SketchEllipse` — Function that returns the specified sketch ellipse using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(centerPoint: Base, majorAxisPoint: Point3D, point: Point3D) -> SketchEllipse` — Creates a sketch ellipse using the center point, a point defining the major axis and a third point anywhere along the ellipse.
    - `centerPoint`: The center point of the ellipse.
    - `majorAxisPoint`: A point3D object that defines both the major axis direction and major axis radius.
    - `point`: A point3D object that the ellipse will pass through.
- prop `count`: int (ro) — Returns the number of ellipses in the sketch.

### SketchEllipticalArcs
The collection of elliptical arcs in a sketch.
- `item(index: int) -> SketchEllipticalArc` — Function that returns the specified sketch elliptical arc using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addByAngle(centerPoint: Base, majorAxis: Vector3D, minorAxis: Vector3D, startAngle: float, sweepAngle: float) -> SketchEllipticalArc` — Creates an elliptical sketch arc where the sweep of the arc is defined by the start and sweep angles.
    - `centerPoint`: The center point of the ellipse.
    - `majorAxis`: The direction of the major axis.
    - `minorAxis`: The direction of the minor axis.
    - `startAngle`: The start angle of the elliptical arc in radians, where 0 is along the major axis.
    - `sweepAngle`: The sweep angle of the elliptical arc in radians, where a positive value is counterclockwise.
- `addByEndPoints(centerPoint: Base, majorAxis: Vector3D, minorAxis: Vector3D, startPoint: Base, endPoint: Base) -> SketchEllipticalArc` — Creates an elliptical sketch arc where the sweep of the arc is defined by two points.
    - `centerPoint`: The center point of the ellipse.
    - `majorAxis`: The direction of the major axis.
    - `minorAxis`: The direction of the minor axis.
    - `startPoint`: The start point of the elliptical arc.
    - `endPoint`: The end point of the elliptical arc.
- prop `count`: int (ro) — Returns the number of elliptical arcs in the sketch.

### SketchEntity
This object represents all geometry in a sketch, including all the various curves, points, and text.
- `deleteMe() -> bool` — Deletes the entity from the sketch.
- prop `parentSketch`: Sketch (ro) — Returns the parent sketch.
- prop `sketchDimensions`: SketchDimensionList (ro) — Returns the sketch dimensions that are attached to this curve.
- prop `geometricConstraints`: GeometricConstraintList (ro) — Returns the sketch constraints that are attached to this curve.
- prop `is2D`: bool (ro) — Indicates if this curve lies entirely on the sketch x-y plane.
- prop `isReference`: bool (rw) — Indicates if this geometry is a reference.
- prop `isFixed`: bool (rw) — Indicates if this geometry is "fixed".
- prop `isVisible`: bool (ro) — When a sketch is created, geometry is sometimes automatically added to the sketch.
- prop `boundingBox`: BoundingBox3D (ro) — Returns the bounding box of the entity in sketch space.
- prop `referencedEntity`: Base (ro) — Returns the referenced entity in the case where IsReference is true.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `isDeletable`: bool (ro) — Indicates if this sketch entity can be deleted.
- prop `isFullyConstrained`: bool (ro) — Indicates if this sketch entity is fully constrained.
- prop `attributes`: Attributes (ro) — Returns the collection of attributes associated with this sketch entity.
- prop `entityToken`: str (ro) — Returns a token for the SketchEntity object.
- prop `isLinked`: bool (ro) — Indicates if this sketch entity was created by a projection, inclusion, or driven by an API script.

### SketchEntityList
A list of sketch entities.
- `item(index: int) -> SketchEntity` — Function that returns the specified sketch entity using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `count`: int (ro) — Returns the number of sketch entities in the list.

### Sketches
Provides access to the sketches within a design and provides methods to create new sketches.
- `item(index: int) -> Sketch` — Function that returns the specified sketch using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `itemByName(name: str) -> Sketch` — Returns the sketch with the specified name.
    - `name`: The name of the sketch as seen in the browser and the timeline.
- `add(planarEntity: Base, occurrenceForCreation: Occurrence = None) -> Sketch` — Creates a new sketch on the specified planar entity.
    - `planarEntity`: A construction plane or planar face that defines the sketch plane
    - `occurrenceForCreation`: A creation occurrence is needed if the planarEntity is in another component AND the sketch is not in the root component.
- `addToBaseOrFormFeature(planarEntity: Base, targetBaseOrFormFeature: Base, includeFaceEdges: bool) -> Sketch` — Creates a parametric sketch that is associated with a base feature.
    - `planarEntity`: A construction plane or planar face that defines the sketch plane.
    - `targetBaseOrFormFeature`: The existing base feature that you want to associate this sketch with.
    - `includeFaceEdges`: When a BrepFace is used as the planarEntity argument, this defines if the edges of the face should be included in the sketch.
- `addWithoutEdges(planarEntity: Base, occurrenceForCreation: Occurrence = None) -> Sketch` — Creates a new sketch on the specified planar entity.
    - `planarEntity`: A construction plane or planar face that defines the sketch plane.
    - `occurrenceForCreation`: A creation occurrence is needed if the planarEntity is in another component AND the sketch is not in the root component.
- prop `count`: int (ro) — Returns the number of sketches in a component.

### SketchFittedSplines
The collection of fitted splines in a sketch.
- `item(index: int) -> SketchFittedSpline` — Function that returns the specified sketch fitted spline using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(fitPoints: ObjectCollection) -> SketchFittedSpline` — Creates a new fitted spline through the specified points.
    - `fitPoints`: A collection of points that the curve will fit through.
- `addBlendCurve(firstCurve: SketchCurve, firstCurvePoint: Point3D, secondCurve: SketchCurve, secondCurvePoint: Point3D, isCurvatureContinuity: bool = False) -> SketchFittedSpline` — Creates a blend curve between two sketch curves.
    - `firstCurve`: The first curve for the blend curve definition.
    - `firstCurvePoint`: A point on or close to one end of the first curve that indicates the end to create the blend curve on.
    - `secondCurve`: The second curve for the blend curve definition.
    - `secondCurvePoint`: A point on or close to one end of the second curve that indicates the end to create the blend curve on.
    - `isCurvatureContinuity`: Optional argument that specifies if a curvature continuous (G2) or a tangent continuous (G1) blend curve is created.
- prop `count`: int (ro) — Returns the number of fitted splines in the sketch.

### SketchFixedSplines
The collection of fixed splines in a sketch.
- `item(index: int) -> SketchFixedSpline` — Function that returns the specified sketch fixed spline using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addByNurbsCurve(nurbsCurve: NurbsCurve3D) -> SketchFixedSpline` — Creates a new fixed spline using the input NurbsCurve3D to define the shape.
    - `nurbsCurve`: A NurbsCurve3D object that defines a valid NURBS curve.
- prop `count`: int (ro) — Returns the number of fitted splines in the sketch.

### SketchIsoparametricCurve
This object represents the result of creating isoparametric curves.
- `setSingle(isPhysical: bool, distance: ValueInput) -> bool` — Redefines that a single isoparametric curve will be created and its position is defined by its distance from the edge of the surface.
    - `isPhysical`: Specifies if the offset of the curve from the edge of the surface is defined by a physical distance or a proportional distance along the surface where it is defined …
    - `distance`: The distance of the curve from the edge of the surface.
- `setDistributed(quantity: ValueInput) -> bool` — Redefines that one or more isoparametric curves will be created along the U or V parameter curves of the face.
    - `quantity`: The number of isoparametric curves to create.
- `deleteMe() -> bool` — Deletes this SketchIsoparametricCurve object.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchIsoparametricCurve` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `face`: BRepFace (rw) — Gets and sets the BRepFace that the curves are calculated for.
- prop `isUDirection`: bool (rw) — Gets and sets the direction of the isoparametric curve on the surface.
- prop `isSingle`: bool (ro) — Gets if a single or distributed curve creation is defined.
- prop `isPhysicalOffset`: bool (ro) — Gets how the distance of the single curve from the face edge is defined by a distance or proportionally.
- prop `quantityOrDistance`: ModelParameter (ro) — Returns the parameter that controls the quantity or offset distance of the curves.
- prop `resultCurves`: list[SketchCurve] (ro) — Returns the sketch curves that were created as isoparametric curves.
- prop `assemblyContext`: Occurrence (ro) — Returns the assembly occurrence (i.e.
- prop `nativeObject`: SketchIsoparametricCurve (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchIsoparametricCurves
The collection of isoparametric curves in a sketch.
- `item(index: int) -> SketchIsoparametricCurve` — Function that returns the specified isoparametric curve using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `createInput(face: BRepFace) -> IsoparametricCurveInput` — Creates a new IsoparametricCurveInput object that is used to specify the input needed to create new isoparametric curves.
    - `face`: The BRepFace on which to create the isoparametric curve.
- `add(input: IsoparametricCurveInput) -> SketchIsoparametricCurve` — Creates sketch geometry that represents isoparametric curves on a face.
    - `input`: The IsoparametricCurveInput object that specifies the input needed to create the isoparametric curve(s).
- `addUnlinked(input: IsoparametricCurveInput) -> list[SketchCurve]` — Creates sketch geometry that represents isoparametric curves on a face.
    - `input`: The IsoparametricCurveInput object that specifies the input needed to create the isoparametric curve(s).
- prop `count`: int (ro) — Returns the number of isoparametric curves in the sketch.

### SketchLineList
A list of sketch lines.
- `item(index: int) -> SketchLine` — Function that returns the specified sketch line using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `count`: int (ro) — Returns the number of sketch lines in the list.

### SketchLines
The collection of lines in a sketch.
- `item(index: int) -> SketchLine` — Function that returns the specified sketch line using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `addByTwoPoints(startPoint: Base, endPoint: Base) -> SketchLine` — Creates a sketch line between the two input points.
    - `startPoint`: The start point of the line.
    - `endPoint`: The end point of the line.
- `addTwoPointRectangle(pointOne: Base, pointTwo: Base) -> SketchLineList` — Creates four sketch lines representing a rectangle where the two points are the opposing corners of the rectangle.
    - `pointOne`: The first corner of the rectangle.
    - `pointTwo`: The second corner of the rectangle.
- `addThreePointRectangle(pointOne: Base, pointTwo: Base, pointThree: Point3D) -> SketchLineList` — Creates four sketch lines representing a rectangle where the first two points are the base corners of the rectangle and the third point defines the height.
    - `pointOne`: The first corner of the rectangle.
    - `pointTwo`: The first corner of the rectangle.
    - `pointThree`: The first corner of the rectangle.
- `addCenterPointRectangle(centerPoint: Point3D, cornerPoint: Base) -> SketchLineList` — Creates four sketch lines representing a rectangle where the first point represents the center of the rectangle.
    - `centerPoint`: The center point of the rectangle
    - `cornerPoint`: The corner of the rectangle.
- `addDistanceChamfer(firstLine: SketchLine, firstLinePoint: Point3D, secondLine: SketchLine, secondLinePoint: Point3D, distanceOne: float, distanceTwo: float) -> SketchLine` — Creates a chamfer between two sketch lines.
    - `firstLine`: The first line you want to chamfer.
    - `firstLinePoint`: A point on the first line that is on the side of the intersection with the second line that you want to keep.
    - `secondLine`: The second line you want to chamfer.
    - `secondLinePoint`: A point on the second line that is on the side of the intersection with the first line that you want to keep.
    - `distanceOne`: Defines the distance of the start point of the chamfer line from the intersection point of the two lines along the first line.
    - `distanceTwo`: Defines the distance of the start point of the chamfer line from the intersection point of the two lines along the second line.
- `addAngleChamfer(firstLine: SketchLine, firstLinePoint: Point3D, secondLine: SketchLine, secondLinePoint: Point3D, distance: float, angle: float) -> SketchLine` — Creates a chamfer between two sketch lines.
    - `firstLine`: The first line you want to chamfer.
    - `firstLinePoint`: A point on the first line that is on the side of the intersection with the second line that you want to keep.
    - `secondLine`: The second line you want to chamfer.
    - `secondLinePoint`: A point on the second line that is on the side of the intersection with the first line that you want to keep.
    - `distance`: Defines the distance of the start point of the chamfer from the intersection point of the two lines along the first line.
    - `angle`: Defines the angle of the chamfer as measured from the first line.
- `addScribedPolygon(centerPoint: Base, edgeCount: int, angle: float, radius: float, isInscribed: bool) -> SketchLineList` — Creates either an inscribed or circumscribed n-sided polygon.
    - `centerPoint`: Either an existing SketchPoint or a Point3D object that defines the center point of the polygon.
    - `edgeCount`: The number of edges in the resulting polygon.
    - `angle`: Controls the rotation of the polygon around the center point.
    - `radius`: The radius of the circle in centimeters that the polygon goes to, either outside (circumscribed) or inside (inscribed) the circle.
    - `isInscribed`: Specifies if a circumscribed or inscribed polygon should be created.
- `addEdgePolygon(pointOne: Base, pointTwo: Base, isRight: bool, edgeCount: int) -> SketchLineList` — Creates a polygon where two points specify an edge of the polygon.
    - `pointOne`: The first point of the edge.
    - `pointTwo`: The second point of the edge.
    - `isRight`: After defining points one and two, a polygon can be created on either side of the line defined by the two points.
    - `edgeCount`: The number of edges in the resulting polygon.
- `addByMidpoint(midPoint: Base, secondPoint: Base) -> SketchLine` — Creates a sketch line where the first point is the midpoint and the second point is one endpoint.
    - `midPoint`: The midpoint of the line.
    - `secondPoint`: One endpoint of the line.
- prop `count`: int (ro) — Returns the number of lines in the sketch.

### SketchPointList
A list of sketch points.
- `item(index: int) -> SketchPoint` — Function that returns the specified sketch point using an index into the collection.
    - `index`: The index of the item within the collection to return.
- prop `count`: int (ro) — Returns the number of sketch points in the list.

### SketchPoints
A collection of sketch points.
- `item(index: int) -> SketchPoint` — Function that returns the specified sketch using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(point: Point3D) -> SketchPoint` — Creates a point at the specified location.
    - `point`: The coordinate location to create the sketch point.
- prop `count`: int (ro) — Returns the number of sketch points in the sketch.

### SketchTextDefinition
The base class for the classes that define how text can be defined.
- prop `parentSketchText`: SketchText (ro) — Returns the SketchText object this definition is associated with.

### SketchTextInput
The SketchTextInput object is equivalent to the Sketch Text dialog in that it collects all of the input required to create sketch text.
- `setAsFitOnPath(path: Base, isAbovePath: bool) -> bool` — Sets this SketchTextInput to define text that fits along a specified path.
    - `path`: The entity that defines the path for the text.
    - `isAbovePath`: Indicates if the text should be positioned above or below the path entity.
- `setAsAlongPath(path: Base, isAbovePath: bool, horizontalAlignment: HorizontalAlignments, characterSpacing: float) -> bool` — Sets this SketchTextInput to define text that follows along a specified path.
    - `path`: The entity that defines the path for the text.
    - `isAbovePath`: Indicates if the text should be positioned above or below the path entity.
    - `horizontalAlignment`: Specifies the horizontal alignment of the text with respect to the path curve.
    - `characterSpacing`: The percentage change in default spacing between characters.
- `setAsMultiLine(cornerPoint: Base, diagonalPoint: Base, horizontalAlignment: HorizontalAlignments, verticalAlignment: VerticalAlignments, characterSpacing: float) -> bool` — Defines the first corner point of the rectangle that will contain the text.
    - `cornerPoint`: Specifies the location of one of the corner points of the rectangle that will contain the text.
    - `diagonalPoint`: Specifies the location of the diagonal point of the rectangle that will contain the text.
    - `horizontalAlignment`: Specifies the horizontal alignment of the text with respect to the text rectangle.
    - `verticalAlignment`: Specifies the vertical alignment of the text with respect to the text rectangle.
    - `characterSpacing`: The spacing between the characters.
- prop `text`: str (rw) — Gets and sets the displayed text.
- prop `fontName`: str (rw) — Gets and sets the name of the font to use.
- prop `textStyle`: TextStyles (rw) — Gets and sets the text style to apply to the entire text.
- prop `isHorizontalFlip`: bool (rw) — Gets and sets if the text is flipped horizontally.
- prop `isVerticalFlip`: bool (rw) — Gets and sets if the text is flipped vertically.
- prop `definition`: SketchTextDefinition (ro) — Returns the SketchTextDefinition object associated with this input.
- prop `expression`: str (rw) — Gets and sets the expression of the parameter that will be created when this SketchText is created.
- prop `height2`: ValueInput (rw) — Gets and sets the ValueInput that defines the height of the text.

### SketchTexts
The collection of text blocks in a sketch.
- `item(index: int) -> SketchText` — Function that returns the specified sketch text using an index into the collection.
    - `index`: The index of the item within the collection to return.
- `add(input: SketchTextInput) -> SketchText` — Creates a sketch text.
    - `input`: A SketchTextInput object created using the SketchTexts.createInput method.
- `createInput3(expression: str, height: ValueInput) -> SketchTextInput` — Creates a SketchTextInput object that is used to define the additional input to create text.
    - `expression`: This defines the expression of the parameter that will be created when this SketchText is created.
    - `height`: A ValueInput that defines the height of the text.
- prop `count`: int (ro) — Returns the number of texts in the sketch.

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

### CoincidentConstraint (GeometricConstraint)
A coincident constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> CoincidentConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `point`: SketchPoint (ro) — Returns the sketch point that is constrained.
- prop `entity`: SketchEntity (ro) — The sketch curve or point the point is constrained to.
- prop `nativeObject`: CoincidentConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### CoincidentToSurfaceConstraint (GeometricConstraint)
A sketch constraint defining that a point is coincident to a surface.
- `createForAssemblyContext(occurrence: Occurrence) -> CoincidentToSurfaceConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `point`: SketchPoint (ro) — Returns the sketch point that is constrained.
- prop `surface`: Base (ro) — Returns the BRepFace or ConstructionPlane the point is constrained to.
- prop `nativeObject`: CoincidentToSurfaceConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### CollinearConstraint (GeometricConstraint)
A collinear constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> CollinearConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `lineOne`: SketchLine (ro) — Returns the first line.
- prop `lineTwo`: SketchLine (ro) — Returns the second line.
- prop `nativeObject`: CollinearConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### ConcentricConstraint (GeometricConstraint)
A concentric constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> ConcentricConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entityOne`: SketchCurve (ro) — Returns the first curve.
- prop `entityTwo`: SketchCurve (ro) — Returns the second curve.
- prop `nativeObject`: ConcentricConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### EqualConstraint (GeometricConstraint)
An equal constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> EqualConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `curveOne`: SketchCurve (ro) — Returns the first curve.
- prop `curveTwo`: SketchCurve (ro) — Returns the second curve.
- prop `nativeObject`: EqualConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### HorizontalConstraint (GeometricConstraint)
A horizontal constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> HorizontalConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `line`: SketchLine (ro) — Returns the line being constrained.
- prop `nativeObject`: HorizontalConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### HorizontalPointsConstraint (GeometricConstraint)
A horizontal constraint between two points in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> HorizontalPointsConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `pointOne`: SketchPoint (ro) — Returns the first point.
- prop `pointTwo`: SketchPoint (ro) — Returns the second point.
- prop `nativeObject`: HorizontalPointsConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### LineOnPlanarSurfaceConstraint (GeometricConstraint)
A sketch constraint defining that a line that lies on a planar face or construction plane.
- `createForAssemblyContext(occurrence: Occurrence) -> LineOnPlanarSurfaceConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `line`: SketchLine (ro) — Returns the SketchLine object that is constrained.
- prop `planarSurface`: Base (ro) — Returns the planar BRepFace or ConstructionPlane the line is constrained to lie on.
- prop `nativeObject`: LineOnPlanarSurfaceConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### LineParallelToPlanarSurfaceConstraint (GeometricConstraint)
A sketch constraint defining that a line is parallel to a planar face or construction plane.
- `createForAssemblyContext(occurrence: Occurrence) -> LineParallelToPlanarSurfaceConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `line`: SketchLine (ro) — Returns the SketchLine object that is constrained.
- prop `planarSurface`: Base (ro) — Returns the planar BRepFace or ConstructionPlane the line is parallel to.
- prop `nativeObject`: LineParallelToPlanarSurfaceConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### MidPointConstraint (GeometricConstraint)
A midpoint constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> MidPointConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `point`: SketchPoint (ro) — Returns the sketch point being constrained.
- prop `midPointCurve`: SketchCurve (ro) — Returns the curve defining the midpoint.
- prop `nativeObject`: MidPointConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

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

### ParallelConstraint (GeometricConstraint)
A parallel constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> ParallelConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `lineOne`: SketchLine (ro) — Returns the first line.
- prop `lineTwo`: SketchLine (ro) — Returns the second line.
- prop `nativeObject`: ParallelConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### PerpendicularConstraint (GeometricConstraint)
A perpendicular constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> PerpendicularConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `nativeObject`: PerpendicularConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `line`: SketchLine (ro) — Returns the line.
- prop `curve`: SketchCurve (ro) — Returns the curve.

### PerpendicularToSurfaceConstraint (GeometricConstraint)
A sketch constraint defining that a curve is perpendicular to a face or construction plane.
- `createForAssemblyContext(occurrence: Occurrence) -> PerpendicularToSurfaceConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `curve`: SketchCurve (ro) — Returns the SketchCurve object that is constrained.
- prop `surface`: Base (ro) — Returns the BRepFace or ConstructionPlane the line is constrained to be perpendicular to.
- prop `nativeObject`: PerpendicularToSurfaceConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### PolygonConstraint (GeometricConstraint)
A polygon constraint in a sketch.
- prop `points`: list[SketchPoint] (ro) — Returns the sketch points that define the vertices of the polygon.
- prop `centerPoint`: SketchPoint (ro) — Returns the SketchPoint that acts as the center point of the polygon.

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

### SketchAngularDimension (SketchDimension)
An angular dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchAngularDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `lineOne`: SketchLine (ro) — The first line being constrained.
- prop `lineTwo`: SketchLine (ro) — The second line being constrained.
- prop `nativeObject`: SketchAngularDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchConcentricCircleDimension (SketchDimension)
A concentric circle dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchConcentricCircleDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `circleOne`: SketchCurve (ro) — Returns the first concentric circle or arc.
- prop `circleTwo`: SketchCurve (ro) — Returns the second concentric circle or arc.
- prop `nativeObject`: SketchConcentricCircleDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchCurve (SketchEntity)
A single sketch curve.
- `split(splitPoint: Point3D, createConstraints: bool = True) -> ObjectCollection` — Split a curve at a position specified along the curve splitPoint : A position (transient Point3D) on the curve that defines the point at which to split the curve createConstraints : Constraints are created by …
    - `splitPoint`: A position (transient Point3D) on the curve that defines the point at which to split the curve
    - `createConstraints`: Constraints are created by default.
- `trim(segmentPoint: Point3D, createConstraints: bool = True) -> ObjectCollection` — Trim a curve by specifying a point that determines the segment of the curve to trim away segmentPoint : A point (transient Point3D) on or closest to the segment of the curve to remove.
    - `segmentPoint`: A point (transient Point3D) on or closest to the segment of the curve to remove.
    - `createConstraints`: Constraints are created by default.
- `breakCurve(segmentPoint: Point3D, createConstraints: bool = True) -> ObjectCollection` — Breaks a curve into two or three pieces by finding intersections of this curve with all other curves in the sketch and splitting this curve at the nearest intersections to a specified point on the …
    - `segmentPoint`: A point that specifies the segment of the curve that is to be split from the rest of the curve.
    - `createConstraints`: Optional argument that specifies if constraints should be created between the new curve segments.
- `extend(endPoint: Point3D, createConstraints: bool = True) -> ObjectCollection` — Extend a curve by specifying a point that determines the end of the curve to extend endPoint : A point (transient Point3D) on or closest to the end of the curve to extend.
    - `endPoint`: A point (transient Point3D) on or closest to the end of the curve to extend.
    - `createConstraints`: Constraints are created by default.
- `intersections(sketchCurves: ObjectCollection) -> tuple[bool, ObjectCollection, ObjectCollection]` — Get the curves that intersect this curve along with the intersection points (Point3D) sketchCurves : A collection of curves to attempt to find intersections with.
    - `sketchCurves`: A collection of curves to attempt to find intersections with.
    - `intersectingCurves`: A collection of the actual intersecting curves
    - `intersectionPoints`: A collection of intersection points (Point3D) Item numbers in this collection correspond to the item numbers in the intersectingCurves collection.
- prop `length`: float (ro) — Returns the length of the curve in centimeters.
- prop `isConstruction`: bool (rw) — Gets and sets whether this curve is construction geometry.

### SketchDiameterDimension (SketchDimension)
An diameter dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchDiameterDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entity`: SketchCurve (ro) — Returns the arc or circle being constrained.
- prop `nativeObject`: SketchDiameterDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchDistanceBetweenLineAndPlanarSurfaceDimension (SketchDimension)
A linear dimension in a sketch between a sketch line and a planar surface.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchDistanceBetweenLineAndPlanarSurfaceDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `line`: SketchLine (ro) — The sketch line being constrained.
- prop `planarSurface`: Base (ro) — The planar surface the dimension is anchored to.
- prop `nativeObject`: SketchDistanceBetweenLineAndPlanarSurfaceDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchDistanceBetweenPointAndSurfaceDimension (SketchDimension)
A linear dimension in a sketch between a sketch point and a surface.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchDistanceBetweenPointAndSurfaceDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `point`: SketchPoint (ro) — The sketch point being constrained.
- prop `surface`: Base (ro) — The BRepFace or ConstructionPlane to which the dimension is anchored.
- prop `nativeObject`: SketchDistanceBetweenPointAndSurfaceDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchEllipseMajorRadiusDimension (SketchDimension)
An ellipse major radius dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchEllipseMajorRadiusDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `ellipse`: SketchCurve (ro) — Returns the ellipse or elliptical arc being constrained.
- prop `nativeObject`: SketchEllipseMajorRadiusDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchEllipseMinorRadiusDimension (SketchDimension)
An ellipse minor radius dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchEllipseMinorRadiusDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `ellipse`: SketchCurve (ro) — Returns the ellipse or elliptical arc being constrained.
- prop `nativeObject`: SketchEllipseMinorRadiusDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchLinearDiameterDimension (SketchDimension)
A linear diameter dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchLinearDiameterDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `line`: SketchLine (ro) — The first line being constrained.
- prop `entityTwo`: SketchEntity (ro) — The second entity being constrained.
- prop `nativeObject`: SketchLinearDiameterDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchLinearDimension (SketchDimension)
A linear dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchLinearDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entityOne`: SketchEntity (ro) — The first entity being constrained.
- prop `entityTwo`: SketchEntity (ro) — The second entity being constrained.
- prop `orientation`: DimensionOrientations (ro) — The orientation of this dimension.
- prop `nativeObject`: SketchLinearDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchOffsetCurvesDimension (SketchDimension)
A SketchOffsetCurvesDimension object is created automatically whenever curves are offset.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchOffsetCurvesDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `offsetConstraint`: OffsetConstraint (ro) — Returns the OffsetConstraint object that defines the curve offset.
- prop `nativeObject`: SketchOffsetCurvesDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchOffsetDimension (SketchDimension)
An offset dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchOffsetDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `line`: SketchLine (ro) — The first line being constrained.
- prop `entityTwo`: SketchEntity (ro) — The second entity being constrained.
- prop `nativeObject`: SketchOffsetDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchPoint (SketchEntity)
A point within a sketch.
- `move(translation: Vector3D) -> bool` — Moves the sketch geometry using the specified transform.
    - `translation`: The vector that defines the distance and direction to move.
- `merge(point: SketchPoint) -> bool` — Merges the input sketch point into this sketch point.
    - `point`: The point to merge with this point.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchPoint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `detach(curve: SketchCurve) -> SketchPoint` — This method disconnects the specified curve from the sketch point.
    - `curve`: The sketch curve to detach from the sketch point.
- prop `geometry`: Point3D (ro) — Returns a Point3D object which provides the position of the sketch point.
- prop `worldGeometry`: Point3D (ro) — Returns a Point3D object which provides the position of the sketch point in world space.
- prop `nativeObject`: SketchPoint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `connectedEntities`: SketchEntityList (ro) — Returns the set of sketch entities that are directly connected to this point.

### SketchPointHolePositionDefinition (HolePositionDefinition)
Provides positioning information for a hole that is positioned by a sketch point.
- prop `sketchPoint`: SketchPoint (ro) — Returns the sketch point that defines the center of the hole.

### SketchPointsBossPositionDefinition (BossPositionDefinition)
Provides positioning information for a boss feature that is positioned by a sketch point(s).
- prop `sketchPoints`: ObjectCollection (ro) — Returns the sketch points that defines the position of the boss feature.

### SketchPointsHolePositionDefinition (HolePositionDefinition)
Provides positioning information for a hole that is positioned by a sketch point.
- prop `sketchPoints`: ObjectCollection (ro) — Returns the sketch point that defines the center of the hole.

### SketchRadialDimension (SketchDimension)
An radial dimension in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchRadialDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entity`: SketchCurve (ro) — The arc or circle being constrained.
- prop `nativeObject`: SketchRadialDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchTangentDistanceDimension (SketchDimension)
A distance dimension measuring to the tangent on one or two circles or arcs.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchTangentDistanceDimension` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entityOne`: SketchEntity (ro) — The first entity being constrained.
- prop `circleOrArc`: SketchCurve (ro) — The second entity being constrained which is always a SketchCircle or SketchArc.
- prop `nativeObject`: SketchTangentDistanceDimension (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchText (SketchEntity)
Text in a sketch.
- `explode() -> list[SketchCurve]` — Explodes the SketchText into a set of curves.
- `asCurves() -> list[Curve3D]` — Returns the underlying curves that define the outline of the text.
- `redefineAsFitOnPath(path: Base, isAbovePath: bool) -> bool` — Sets this SketchTextInput to define text that fits along a specified path.
    - `path`: The entity that defines the path for the text.
    - `isAbovePath`: Indicates if the text should be positioned above or below the path entity.
- `redefineAsAlongPath(path: Base, isAbovePath: bool, horizontalAlignment: HorizontalAlignments, characterSpacing: float) -> bool` — Sets this SketchTextInput to define text that follows along a specified path.
    - `path`: The entity that defines the path for the text.
    - `isAbovePath`: Indicates if the text should be positioned above or below the path entity.
    - `horizontalAlignment`: Specifies the horizontal alignment of the text with respect to the path curve.
    - `characterSpacing`: The spacing between the characters.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchText` — Creates a proxy object for the SketchText object that represents the SketchText object in the context of an assembly.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `fontName`: str (rw) — Gets and sets the name of the font to use.
- prop `textStyle`: TextStyles (rw) — Gets and sets the text style to apply to the entire text.
- prop `isHorizontalFlip`: bool (rw) — Gets and sets if the text is flipped horizontally.
- prop `isVerticalFlip`: bool (rw) — Gets and sets if the text is flipped vertically.
- prop `definition`: SketchTextDefinition (ro) — Gets the definition that is currently used to specify how the sketch text is defined.
- prop `nativeObject`: SketchText (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `textParameter`: ModelParameter (ro) — Returns the model parameter that was created when the sketch text was created that controls the contents of the sketch text.
- prop `heightParameter`: ModelParameter (ro) — Returns the model parameter that was created when the sketch text was created that controls the height of the sketch text.

### SmoothConstraint (GeometricConstraint)
A smooth constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SmoothConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `curveOne`: SketchCurve (ro) — Returns the first curve.
- prop `curveTwo`: SketchCurve (ro) — Returns the second curve.
- prop `nativeObject`: SmoothConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SymmetryConstraint (GeometricConstraint)
A symmetry constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SymmetryConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `entityOne`: SketchEntity (ro) — Returns the first curve.
- prop `entityTwo`: SketchEntity (ro) — Returns the second curve.
- prop `symmetryLine`: SketchLine (ro) — Returns the axis (SketchLine) that defines the symmetry.
- prop `nativeObject`: SymmetryConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### TangentConstraint (GeometricConstraint)
A tangent constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> TangentConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `curveOne`: SketchCurve (ro) — Returns the first curve.
- prop `curveTwo`: SketchCurve (ro) — Returns the second curve.
- prop `nativeObject`: TangentConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### VerticalConstraint (GeometricConstraint)
A vertical constraint in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> VerticalConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `line`: SketchLine (ro) — Returns the line being constrained.
- prop `nativeObject`: VerticalConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### VerticalPointsConstraint (GeometricConstraint)
A vertical constraint between two points in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> VerticalPointsConstraint` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `pointOne`: SketchPoint (ro) — Returns the first point.
- prop `pointTwo`: SketchPoint (ro) — Returns the second point.
- prop `nativeObject`: VerticalPointsConstraint (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchArc (SketchCurve)
An arc in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchArc` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `centerSketchPoint`: SketchPoint (ro) — The sketch point at the center of the arc.
- prop `startSketchPoint`: SketchPoint (ro) — The sketch point at the start of the arc.
- prop `endSketchPoint`: SketchPoint (ro) — The sketch point at the end of the arc.
- prop `radius`: float (rw) — Gets and sets the radius of the arc.
- prop `geometry`: Arc3D (ro) — Returns the transient geometry of the arc which provides geometric information about the arc.
- prop `worldGeometry`: Arc3D (ro) — Returns an Arc3D object which provides geometric information in world space.
- prop `nativeObject`: SketchArc (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchCircle (SketchCurve)
A circle in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchCircle` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `centerSketchPoint`: SketchPoint (ro) — Returns the sketch point at the center of the circle.
- prop `geometry`: Circle3D (ro) — Returns the transient geometry of the circle which provides geometric information about the circle.
- prop `worldGeometry`: Circle3D (ro) — Returns a Point3D object which provides the position of the sketch point in world space.
- prop `area`: float (ro) — Returns the area of the circle in square centimeters.
- prop `radius`: float (rw) — Gets and sets the radius of the circle.
- prop `nativeObject`: SketchCircle (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchConicCurve (SketchCurve)
The SketchConicCurve class represents conic curves in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchConicCurve` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `startSketchPoint`: SketchPoint (ro) — The sketch point at the start of the curve.
- prop `endSketchPoint`: SketchPoint (ro) — The sketch point at the end of the curve.
- prop `apexSketchPoint`: SketchPoint (ro) — The sketch point at the apex of the conic curve.
- prop `geometry`: NurbsCurve3D (ro) — Returns the transient geometry of the curve which provides geometric information about the curve.
- prop `worldGeometry`: NurbsCurve3D (ro) — Returns a NurbsCurve3D object that is the equivalent of this sketch curve but is in the space of the parent component rather than in sketch space.
- prop `evaluator`: CurveEvaluator3D (ro) — Returns an evaluator object that lets you perform evaluations on the precise geometry of the curve.
- prop `nativeObject`: SketchConicCurve (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `rhoValue`: float (rw) — Get and sets the rho value for the curve.

### SketchControlPointSpline (SketchCurve)
A control point spline in a sketch.
- `addControlPoint(parameter: float) -> bool` — Adds an additional control point to the control point spline.
    - `parameter`: The parameter position that defines where to insert the new control point.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchControlPointSpline` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `startSketchPoint`: SketchPoint (ro) — The sketch point at the start of the spline.
- prop `endSketchPoint`: SketchPoint (ro) — The sketch point at the end of the spline.
- prop `controlPoints`: list[SketchPoint] (ro) — Returns the set of sketch points that the control frame of the spline fits through.
- prop `geometry`: NurbsCurve3D (ro) — Returns the transient geometry of the curve which provides geometric information about the curve.
- prop `worldGeometry`: NurbsCurve3D (ro) — Returns a NurbsCurve3D object that is the equivalent of this sketch curve but is in the space of the parent component rather than in sketch space.
- prop `evaluator`: CurveEvaluator3D (ro) — Returns an evaluator object that lets you perform evaluations on the precise geometry of the curve.
- prop `nativeObject`: SketchControlPointSpline (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `degree`: SplineDegrees (rw) — Gets and sets the degree of the spline.
- prop `isControlFrameDisplayed`: bool (rw) — Gets and sets if the control frame of the curve is currently displayed.
- prop `controlFrameLines`: list[SketchLine] (ro) — Returns the sketch lines that represent the control frame of the spline.

### SketchEllipse (SketchCurve)
An ellipse in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchEllipse` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `centerSketchPoint`: SketchPoint (ro) — Returns the sketch point that defines the center of the ellipse.
- prop `majorAxis`: Vector3D (rw) — Gets and sets the major axis direction of the ellipse.
- prop `majorAxisRadius`: float (rw) — Gets and sets the major axis radius of the ellipse.
- prop `minorAxisRadius`: float (rw) — Gets and sets the minor axis radius of the ellipse.
- prop `geometry`: Ellipse3D (ro) — Returns the transient geometry of the ellipse which provides geometric information about the ellipse.
- prop `worldGeometry`: Ellipse3D (ro) — Returns an Ellipse3D object which provides geometric information in world space.
- prop `nativeObject`: SketchEllipse (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `majorAxisLine`: SketchLine (ro) — Returns the sketch line associated with the ellipse that lies along the major axis.
- prop `minorAxisLine`: SketchLine (ro) — Returns the sketch line associated with the ellipse that lies along the minor axis.

### SketchEllipticalArc (SketchCurve)
An elliptical arc in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchEllipticalArc` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `centerSketchPoint`: SketchPoint (ro) — Gets the sketch point that defines the center of the elliptical arc.
- prop `startSketchPoint`: SketchPoint (ro) — Gets the sketch point that defines the start of the elliptical arc.
- prop `endSketchPoint`: SketchPoint (ro) — Gets the sketch point that defines the end of the elliptical arc.
- prop `majorAxis`: Vector3D (rw) — Gets and sets the major axis direction of the elliptical arc.
- prop `majorAxisRadius`: float (rw) — Gets and sets the major axis radius of the elliptical arc.
- prop `minorAxisRadius`: float (rw) — Gets and sets the minor axis radius of the elliptical arc.
- prop `geometry`: EllipticalArc3D (ro) — Returns the transient geometry of the elliptical arc which provides geometric information about the elliptical arc.
- prop `worldGeometry`: EllipticalArc3D (ro) — Returns an EllipticalArc3D object which provides geometric information in world space.
- prop `nativeObject`: SketchEllipticalArc (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchFittedSpline (SketchCurve)
A fitted spline in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchFittedSpline` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `activateTangentHandle(fitPoint: SketchPoint) -> SketchLine` — Activates the tangent handle for the specified fit point and returns the sketch line that acts as the handle to control the tangency.
    - `fitPoint`: The fit point on the curve where you want to activate the tangent handle.
- `getTangentHandle(fitPoint: SketchPoint) -> SketchLine` — Returns the sketch line that acts as the handle to control the tangency at the specified fit point.
    - `fitPoint`: The fit point on the curve where you want to get the tangent handle.
- `activateCurvatureHandle(fitPoint: SketchPoint) -> SketchArc` — Activates the curvature handle for the specified fit point and returns the sketch arc that acts as the handle to control the curvature.
    - `fitPoint`: The fit point on the curve where you want to activate the curvature handle.
- `getCurvatureHandle(fitPoint: SketchPoint) -> SketchArc` — Returns the sketch arc that acts as the handle to control the curvature at the specified fit point.
    - `fitPoint`: The fit point on the curve where you want to get the curvature handle.
- `addFitPoint(parameter: float) -> SketchPoint` — Creates a new fit point at the specified parameter value.
    - `parameter`: The parameter value at the position along the curve where you want to add the new fit point.
- prop `startSketchPoint`: SketchPoint (ro) — Returns the sketch point that defines the starting position of the spline.
- prop `endSketchPoint`: SketchPoint (ro) — Returns the sketch point that defines the ending position of the spline.
- prop `fitPoints`: SketchPointList (ro) — Returns the set of sketch points that the spline fits through.
- prop `isClosed`: bool (rw) — Gets and sets if this spline is closed.
- prop `geometry`: NurbsCurve3D (ro) — Returns the transient geometry of the curve which provides geometric information about the curve.
- prop `worldGeometry`: NurbsCurve3D (ro) — Returns a NurbsCurve3D object which provides geometric information in world space.
- prop `nativeObject`: SketchFittedSpline (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchFixedSpline (SketchCurve)
The SketchFixedSpline class represents splines in a sketch that are not editable.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchFixedSpline` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- `replaceGeometry(nurbsCurve: NurbsCurve3D) -> bool` — Replaces the underlying NURBS curve that defines the shape of the fixed curve.
    - `nurbsCurve`: A NurbsCurve3D object that defines a valid NURBS curve and will be used to replace the existing geometry definition.
- prop `startSketchPoint`: SketchPoint (ro) — The sketch point at the start of the spline.
- prop `endSketchPoint`: SketchPoint (ro) — The sketch point at the end of the spline.
- prop `geometry`: NurbsCurve3D (ro) — Returns the transient geometry of the curve which provides geometric information about the curve.
- prop `worldGeometry`: NurbsCurve3D (ro) — Returns a NurbsCurve3D object that is the equivalent of this sketch curve but is in the space of the parent component rather than in sketch space.
- prop `evaluator`: CurveEvaluator3D (ro) — Returns an evaluator object that lets you perform evaluations on the precise geometry of the curve.
- prop `nativeObject`: SketchFixedSpline (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.

### SketchLine (SketchCurve)
A line in a sketch.
- `createForAssemblyContext(occurrence: Occurrence) -> SketchLine` — Creates or returns a proxy for the native object - i.e.
    - `occurrence`: The occurrence that defines the context to create the proxy in.
- prop `startSketchPoint`: SketchPoint (ro) — The sketch point at the start of the line.
- prop `endSketchPoint`: SketchPoint (ro) — The sketch point at the end of the line.
- prop `geometry`: Line3D (ro) — Returns the transient geometry of the line which provides geometry information about the line.
- prop `worldGeometry`: Line3D (ro) — Returns a Line3D object which provides geometric information in world space.
- prop `nativeObject`: SketchLine (ro) — The NativeObject is the object outside the context of an assembly and in the context of its parent component.
- prop `isCenterLine`: bool (rw) — Gets and sets whether this line is defined as a centerline.
