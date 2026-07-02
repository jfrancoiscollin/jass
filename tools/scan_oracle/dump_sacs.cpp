#include <iostream>
#include <string>
#include "common.hpp"
#include "libmy.hpp"
#include "bit.hpp"
#include "hash.hpp"
#include "pos.hpp"
#include "var.hpp"
#include "fen.hpp"
#include "gen.hpp"
#include "list.hpp"
#include "move.hpp"
int main() {
   bit::init(); hash::init(); pos::init(); var::init();
   std::string line;
   while (std::getline(std::cin, line)) {
      if (line.empty()) continue;
      Pos pos = pos_from_hub(line);
      List list;
      add_sacs(list, pos);
      std::cout << "SACS " << list.size();
      for (int i = 0; i < list.size(); i++) {
         Move mv = list.move(i);
         std::cout << " " << square_to_std(move::from(mv, pos))
                   << "-" << square_to_std(move::to(mv, pos));
      }
      std::cout << "\n" << std::flush;
   }
   return 0;
}
