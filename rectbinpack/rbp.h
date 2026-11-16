struct RectSize {
	int width;
	int height;
	int id;
};

struct Rect {
	int x;
	int y;
	int width;
	int height;
	int id;
};

enum MaxRectsFreeRectChoiceHeuristic {
	RbpBestShortSideFit, ///< -BSSF: Positions the rectangle against the short side of a free rectangle into which it fits the best.
	RbpBestLongSideFit, ///< -BLSF: Positions the rectangle against the long side of a free rectangle into which it fits the best.
	RbpBestAreaFit, ///< -BAF: Positions the rectangle into the smallest free rect into which it fits.
	RbpBottomLeftRule, ///< -BL: Does the Tetris placement.
	RbpContactPointRule ///< -CP: Choosest the placement where the rectangle touches other rects as much as possible.
};

extern int MaxRectsBestShortSideFit;
extern int MaxRectsBestLongSideFit;
extern int MaxRectsBestAreaFit;
extern int MaxRectsBottomLeftRule;
extern int MaxRectsContactPointRule;

void MaxRects_init(int width, int height, bool flip);
struct Rect MaxRects_insertOne(int width, int height, enum MaxRectsFreeRectChoiceHeuristic method);
unsigned int MaxRects_insert(struct RectSize *sizes, int num, enum MaxRectsFreeRectChoiceHeuristic method, struct Rect **out);
float MaxRects_occupancy();
