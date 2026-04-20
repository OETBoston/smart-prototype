# Known Limitations
A small percentage of curb lines are not generated perfectly and may affect downstream processes.
Manual cleanup may be required to address the edge cases described below.

## 1. Inconsistent Roadway Widths Across Connected Segments
In a small percentage of roadways, width values in the roadway inventory differ between adjacent, 
connected roadway segments.
This can result in curb segments appearing disjointed even when they are continuous in reality.

* If the width difference is within the line merge threshold, adjacent curb segments are connected by a straight line 
from the end of one segment to the start of the next. 
* If the width difference exceeds the merge threshold, the curb segments remain disjointed.
<p align="left">
  <img width="602" height="323" alt="image" src="../images/known-limitations/case-1.png" /><br>
  <em>Figure 1: Example showing disjointed adjacent curb segments caused by inconsistent roadway widths.</em>
</p>


## 2. Overpasses and Underpasses
Areas where roadway centerlines intersect overpasses or underpasses may incorrectly appear to have missing curb 
segments.

* This typically occurs when the overlapping roadway has been excluded (e.g., due to functional class filtering).
* When overpasses or underpasses are excluded consistently, curb segments behave as expected.
<p align="left">
  <img width="602" height="323" alt="image" src="../images/known-limitations/case-2.png" /><br>
  <em>Figure 2: Example showing curb removal near an underpass.</em>
</p>


## 3. Non-orthogonal Intersections
At intersections where roadways connect at non-90-degree angles, 
small slivers or protruding curb fragments may be generated.
<br>
<br>
These artifacts are often caused by:
* Differing roadway widths, and 
* Angular geometry interactions during buffer and overlay operations.
<p align="left">
  <img width="602" height="323" alt="image" src="../images/known-limitations/case-3.png" /><br>
  <em>Figure 3: Example showing small sliver artifacts at non-orthogonal intersections.</em>
</p>
