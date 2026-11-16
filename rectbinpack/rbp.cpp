#include "MaxRectsBinPack.h"
#include <vector>

extern "C" {
#include "rbp.h"
}

rbp::MaxRectsBinPack mbp;

std::vector<rbp::Rect> dst;

int MaxRectsBestShortSideFit = rbp::MaxRectsBinPack::RectBestShortSideFit; ///< -BSSF: Positions the rectangle against the short side of a free rectangle into which it fits the best.
int MaxRectsBestLongSideFit = rbp::MaxRectsBinPack::RectBestLongSideFit; ///< -BLSF: Positions the rectangle against the long side of a free rectangle into which it fits the best.
int MaxRectsBestAreaFit = rbp::MaxRectsBinPack::RectBestAreaFit; ///< -BAF: Positions the rectangle into the smallest free rect into which it fits.
int MaxRectsBottomLeftRule = rbp::MaxRectsBinPack::RectBottomLeftRule; ///< -BL: Does the Tetris placement.
int MaxRectsContactPointRule = rbp::MaxRectsBinPack::RectContactPointRule; ///< -CP: Choosest the placement where the rectangle touches other rects as much as possible.


extern "C" {

void MaxRects_init(int width, int height, bool flip) {
    mbp.Init(width, height, flip);
}

struct Rect MaxRects_insertOne(int width, int height, enum MaxRectsFreeRectChoiceHeuristic method) {
	rbp::Rect packed = mbp.Insert(
		width, height, (rbp::MaxRectsBinPack::FreeRectChoiceHeuristic)method);
	return {packed.x, packed.y, packed.width, packed.height, packed.id};
}

unsigned int MaxRects_insert(struct RectSize *sizes, int num, enum MaxRectsFreeRectChoiceHeuristic method, struct Rect **out) {
	std::vector<rbp::RectSize> rects;
	rects.reserve(num);
	for (int i = 0; i < num; ++i) {
		rects.push_back({sizes[i].width, sizes[i].height, sizes[i].id});
	}
	mbp.Insert(rects, dst, (rbp::MaxRectsBinPack::FreeRectChoiceHeuristic)method);
	*out = reinterpret_cast<struct Rect *>(dst.data());
	return dst.size();
}

float MaxRects_occupancy() {
	return mbp.Occupancy();
}

}
