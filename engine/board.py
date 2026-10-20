from engine.pieces import King, Queen, Rook, Bishop, Knight, Pawn, Rock
X, Y, Z = 0, 1, 2

# Off the Ground, pawns start in Space (z=2) and the Abyss (z=-2) on these files, (x, z)
EXTRA_PAWN_SQUARES = [(1, 2), (6, 2), (1, -2), (6, -2)]
ARMY_SIZE = 24   # pieces each side starts with on the full board

# Portal layouts are mirror images for the two sides: flipping the ranks (rank 1 <-> rank 8)
# turns one pair into the other, so neither side starts closer to a portal.
# Classic: Space a4 <-> Abyss h5, and its mirror Space a5 <-> Abyss h4, linking the top
# layer's a file with the bottom layer's h file.
CLASSIC_PORTALS = [((0, 3, 2), (7, 4, -2)), ((0, 4, 2), (7, 3, -2))]


def mirrored(cell, size=8):
    x, y, z = cell
    return (x, size - 1 - y, z)


def shuffled_portals(rng, board):
    """Two random portal pairs, mirrored for the two sides: each pair joins two different
    layers off the Ground, in the middle four ranks, away from rocks"""
    size = board.size
    cells = [(x, y, z) for z in range(board.z_min, board.z_max + 1) if z != 0
             for y in range(2, size - 2) for x in range(size)
             if type(board.board.get((x, y, z))).__name__ != "Rock"]
    while True:
        first = rng.choice(cells)
        second = rng.choice([cell for cell in cells if cell[2] != first[2]])
        pairs = [(first, second), (mirrored(first, size), mirrored(second, size))]
        if len({cell for pair in pairs for cell in pair}) == 4:
            return pairs

class Board:
    def __init__(self, size=8, z_min=-2, z_max=2):
        # size x size squares per layer, layers z_min..z_max (the Ground is z=0)
        self.size = size
        self.z_min = z_min
        self.z_max = z_max
        self.bounds = (size, z_min, z_max)
        self.board = dict()
        # Portals: each portal cell -> the other cell of its pair (see set_portals)
        self.portals = {}
        # Only the full board has a starting position and rock layout;
        # smaller boards (lessons, scenarios) start empty and are filled in
        if self.is_standard():
            self.init_pieces()
            self.init_rocks()
    
    def set_portals(self, pairs):
        """Link pairs of cells as portals: [((x,y,z), (x,y,z)), ...]. A piece ending its move on
        an empty portal comes out on the other cell of the pair (see GameState). Portal cells
        must be inside the board, distinct, and free of rocks."""
        portals = {}
        for pair in pairs:
            a, b = (tuple(cell) for cell in pair)
            for cell in (a, b):
                self.is_valid_coordinate(cell)
                if cell in portals:
                    raise ValueError("A cell can be one portal only")
                if type(self.board.get(cell)).__name__ == "Rock":
                    raise ValueError("A portal cannot be on a rock")
            if a == b:
                raise ValueError("A portal pair needs two different cells")
            portals[a], portals[b] = b, a
        self.portals = portals

    def portal_pairs(self):
        """The portal pairs, each once, in a stable order"""
        return sorted({tuple(sorted((a, b))) for a, b in self.portals.items()})

    def is_standard(self):
        return self.bounds == (8, -2, 2)
                        
    def is_valid_coordinate(self, coord:tuple):
        if not self.is_coordinate_in_board(coord):
            raise ValueError("Invalid coordiante")

    def is_coordinate_in_board(self,coord:tuple):
        return ( 0 <= coord[X] < self.size and 0 <= coord[Y] < self.size and
                self.z_min <= coord[Z] <= self.z_max)
    
    def get_piece(self, coord:tuple):
        self.is_valid_coordinate(coord)
        return self.board.get(coord)
    
    def set_piece(self, Piece, coord):
        self.is_valid_coordinate(coord)
        if self.board.get(coord) is None:
            self.board[coord] = Piece
        else:
            raise ValueError("coordinate isn't free")
    
    def remove_piece(self,coord):
        self.is_valid_coordinate(coord)
        if self.board.get(coord) is None:
            raise ValueError("Trying to remove a piece from empty coordinate")
        else:
            del self.board[coord]  
            
    def move_piece(self, from_coord: tuple, to_coord: tuple):
        self.is_valid_coordinate(from_coord)
        self.is_valid_coordinate(to_coord)
        
        if self.board.get(from_coord) is None:
            raise ValueError("No piece at source")
        if self.board.get(to_coord) is not None:
            raise ValueError("Destination occupied")
        
        piece = self.board[from_coord]
        del self.board[from_coord]
        self.board[to_coord] = piece
    
    def init_pieces(self): 
        ## White placement
        self.board[(0,0,0)] = Rook("white")
        self.board[(1,0,0)] = Knight("white")
        self.board[(2,0,0)] = Bishop("white")
        self.board[(3,0,0)] = Queen("white")
        self.board[(4,0,0)] = King("white")
        self.board[(5,0,0)] = Bishop("white")
        self.board[(6,0,0)] = Knight("white")
        self.board[(7,0,0)] = Rook("white")
        for i in range(8):
            self.board[(i,1,0)] = Pawn("white")
        
        ## Black placement   
        self.board[(0,7,0)] = Rook("black")
        self.board[(1,7,0)] = Knight("black")
        self.board[(2,7,0)] = Bishop("black")
        self.board[(3,7,0)] = Queen("black")
        self.board[(4,7,0)] = King("black")
        self.board[(5,7,0)] = Bishop("black")
        self.board[(6,7,0)] = Knight("black")
        self.board[(7,7,0)] = Rook("black")
        for i in range(8):
            self.board[(i,6,0)] = Pawn("black")
        
        ## Off the Ground: two knights each in the Dungeon and two bishops each in the Sky
        for x in (1, 6):
            self.board[(x,0,-1)] = Knight("white")
            self.board[(x,7,-1)] = Knight("black")
        for x in (2, 5):
            self.board[(x,0,1)] = Bishop("white")
            self.board[(x,7,1)] = Bishop("black")

        ## Two pawns each in Space and in the Abyss, on the b and g files: clear of the rocks
        for x, z in EXTRA_PAWN_SQUARES:
            self.board[(x,1,z)] = Pawn("white")
            self.board[(x,6,z)] = Pawn("black")
                      
    def init_rocks(self):
        # Layer -1: Hourglass
        self.board[(2, 2, -1)] = Rock()
        self.board[(5, 2, -1)] = Rock()
        self.board[(3, 3, -1)] = Rock()
        self.board[(4, 3, -1)] = Rock()
        self.board[(3, 4, -1)] = Rock()
        self.board[(4, 4, -1)] = Rock()
        self.board[(2, 5, -1)] = Rock()
        self.board[(5, 5, -1)] = Rock()
        
        # Layer -2: Cross
        self.board[(3, 2, -2)] = Rock()
        self.board[(4, 2, -2)] = Rock()
        self.board[(2, 3, -2)] = Rock()
        self.board[(5, 3, -2)] = Rock()
        self.board[(2, 4, -2)] = Rock()
        self.board[(5, 4, -2)] = Rock()
        self.board[(3, 5, -2)] = Rock()
        self.board[(4, 5, -2)] = Rock()

