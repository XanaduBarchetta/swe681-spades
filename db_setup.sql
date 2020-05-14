--
-- This script performs initial setup of the database.
--

CREATE TABLE User
(
    user_id INT AUTO_INCREMENT NOT NULL,
    username VARCHAR(32) NOT NULL,
    password BINARY(60) NOT NULL,
    wins INT DEFAULT 0 NOT NULL,
    losses INT DEFAULT 0 NOT NULL,
    CONSTRAINT User_pk
        PRIMARY KEY (user_id)
);
CREATE UNIQUE INDEX User_username_uindex ON User (username);
-- A User record is equivalent to a player

CREATE TABLE Game
(
    game_id INT AUTO_INCREMENT NOT NULL,
    player_north INT DEFAULT NULL,
    player_south INT DEFAULT NULL,
    player_east INT DEFAULT NULL,
    player_west INT DEFAULT NULL,
    last_activity DATETIME NOT NULL,
    state ENUM('FILLING','IN_PROGRESS','ABANDONED','FORFEITED','COMPLETED') NOT NULL DEFAULT 'FILLING',
    ns_win TINYINT(1) DEFAULT NULL,
    CONSTRAINT Game_pk
        PRIMARY KEY (game_id),
    CONSTRAINT Game_User_fk1
        FOREIGN KEY (player_north) REFERENCES User (`user_id`)
            ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT Game_User_fk2
        FOREIGN KEY (player_south) REFERENCES User (`user_id`)
            ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT Game_User_fk3
        FOREIGN KEY (player_east) REFERENCES User (`user_id`)
            ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT Game_User_fk4
        FOREIGN KEY (player_west) REFERENCES User (`user_id`)
            ON UPDATE CASCADE ON DELETE SET NULL
);
-- Each record in the Game table is a single instance of a game of spades
-- last_activity represents last time at which game had an update
--    updates include player joining game, card being played, and game changing state
-- 'ABANDONED' state denotes a game which never filled all four player slots
-- 'FORFEITED' state denotes a game in which some player timed out on their turn
-- Games in the 'FILLING' state should time out some amount of time relative to last_activity
-- Who won? When state is 'FORFEITED' or 'COMPLETED', check ns_win value to see if North/South team won.
--          If ns_win=True, then North/South team won. If ns_win=False, then East/West team won.
-- There are no ties/draws. The only end state without a win or loss is 'ABANDONED' which does not count towards total games played for a player.

CREATE TABLE Hand
(
    game_id INT NOT NULL,
    hand_number INT NOT NULL,
    dealer ENUM('NORTH','SOUTH','EAST','WEST') NOT NULL,
    north_bid INT DEFAULT NULL,
    south_bid INT DEFAULT NULL,
    east_bid INT DEFAULT NULL,
    west_bid INT DEFAULT NULL,
    spades_broken TINYINT(1) NOT NULL DEFAULT FALSE,
    ns_bags_at_end INT DEFAULT NULL,
    ew_bags_at_end INT DEFAULT NULL,
    ns_score_after_bags INT DEFAULT NULL,
    ew_score_after_bags INT DEFAULT NULL,
    CONSTRAINT Hand_pk
        PRIMARY KEY (game_id, hand_number),
    CONSTRAINT Hand_Game_fk
        FOREIGN KEY (game_id) REFERENCES Game (`game_id`)
            ON UPDATE CASCADE ON DELETE CASCADE
);
-- Each record in the Hand table is a single hand (or "round") of a specific Game of spades
-- hand_number starts at 1 (one), marks the order of hands in a Game
-- Blind bidding is not supported in this model. Players can bid Nil (0), or 1 through 13.
-- dealer for hand_number=1 should be determined randomly. Thereafter, dealer rotates clockwise.

CREATE TABLE HandCard
(
    game_id INT NOT NULL,
    hand_number INT NOT NULL,
    user_id INT NOT NULL,
    card CHAR(3) NOT NULL,
    played TINYINT(1) NOT NULL DEFAULT FALSE,
    CONSTRAINT HandCard_pk
        PRIMARY KEY (game_id, hand_number, user_id, card),
    CONSTRAINT HandCard_Hand_fk
        FOREIGN KEY (game_id, hand_number) REFERENCES Hand (game_id, hand_number),
    CONSTRAINT HandCard_User_fk
        FOREIGN KEY (user_id) REFERENCES User (user_id)
);

CREATE TABLE Trick
(
    game_id INT NOT NULL,
    hand_number INT NOT NULL,
    trick_number INT NOT NULL,
    lead_player ENUM('NORTH','SOUTH','EAST','WEST') NOT NULL,
    lead_suit ENUM('S','H','C','D') DEFAULT NULL,
    north_play CHAR(3) DEFAULT NULL,
    south_play CHAR(3) DEFAULT NULL,
    east_play CHAR(3) DEFAULT NULL,
    west_play CHAR(3) DEFAULT NULL,
    winner ENUM('NORTH','SOUTH','EAST','WEST') DEFAULT NULL,
    CONSTRAINT Trick_pk
        PRIMARY KEY (game_id, hand_number, trick_number),
    CONSTRAINT Trick_Hand_fk
        FOREIGN KEY (game_id, hand_number) REFERENCES Hand (game_id, hand_number)
);
-- trick_number works just like hand_number from Hand description
-- lead_player is 1 clockwise of Hand.dealer for trick_number==1

--
-- This event manages timing out games due to inactivity
--
CREATE EVENT spades_game_timeout
ON SCHEDULE AT CURRENT_TIMESTAMP + INTERVAL 1 HOUR DO
BEGIN
    DECLARE done INT DEFAULT FALSE;
    DECLARE gameid INT;
    DECLARE pnorth, psouth, peast, pwest INT;
    DECLARE leaddir ENUM('NORTH','SOUTH','EAST','WEST');
    DECLARE nplay, splay, eplay, wplay CHAR(3);
    DECLARE cur1 CURSOR FOR SELECT game_id, player_north, player_south, player_east, player_west
        FROM Game WHERE state='IN_PROGRESS' AND last_activity + INTERVAL 1 HOUR < CURRENT_TIMESTAMP;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;

    UPDATE Game SET state='ABANDONED' WHERE state='FILLING' AND last_activity + INTERVAL 1 HOUR < CURRENT_TIMESTAMP;

    OPEN cur1;
    read_loop: LOOP
        FETCH cur1 INTO gameid, pnorth, psouth, peast, pwest;
        IF done THEN
            LEAVE read_loop;
        END IF;
        SELECT lead_player, north_play, south_play, east_play, west_play
            INTO leaddir, nplay, splay, eplay, wplay
        FROM Trick
            WHERE game_id=gameid
            ORDER BY hand_number DESC, trick_number DESC LIMIT 1;
        IF nplay IS NULL AND splay IS NULL AND eplay IS NULL AND wplay IS NULL THEN
            -- Trick leader timed out
            IF leaddir = 'NORTH' OR leaddir = 'SOUTH' THEN
                UPDATE Game SET state='FORFEITED', ns_win=0 WHERE game_id=gameid;
                UPDATE User SET losses=losses+1 WHERE user_id IN (pnorth, psouth);
                UPDATE User SET wins=wins+1 WHERE user_id IN (peast, pwest);
            ELSEIF leaddir = 'EAST' OR leaddir = 'WEST' THEN
                UPDATE Game SET state='FORFEITED', ns_win=1 WHERE game_id=gameid;
                UPDATE User SET losses=losses+1 WHERE user_id IN (peast, pwest);
                UPDATE User SET wins=wins+1 WHERE user_id IN (pnorth, psouth);
            END IF;
        ELSEIF nplay IS NOT NULL AND eplay IS NULL THEN
            -- East timed out
            UPDATE Game SET state='FORFEITED', ns_win=1 WHERE game_id=gameid;
            UPDATE User SET losses=losses+1 WHERE user_id IN (peast, pwest);
            UPDATE User SET wins=wins+1 WHERE user_id IN (pnorth, psouth);
        ELSEIF splay IS NOT NULL AND wplay IS NULL THEN
            -- West timed out
            UPDATE Game SET state='FORFEITED', ns_win=1 WHERE game_id=gameid;
            UPDATE User SET losses=losses+1 WHERE user_id IN (peast, pwest);
            UPDATE User SET wins=wins+1 WHERE user_id IN (pnorth, psouth);
        ELSEIF eplay IS NOT NULL AND splay IS NULL THEN
            -- South timed out
            UPDATE Game SET state='FORFEITED', ns_win=0 WHERE game_id=gameid;
            UPDATE User SET losses=losses+1 WHERE user_id IN (pnorth, psouth);
            UPDATE User SET wins=wins+1 WHERE user_id IN (peast, pwest);
        ELSEIF wplay IS NOT NULL AND nplay IS NULL THEN
            -- North timed out
            UPDATE Game SET state='FORFEITED', ns_win=0 WHERE game_id=gameid;
            UPDATE User SET losses=losses+1 WHERE user_id IN (pnorth, psouth);
            UPDATE User SET wins=wins+1 WHERE user_id IN (peast, pwest);
        END IF;
    END LOOP;

    CLOSE cur1;
END;