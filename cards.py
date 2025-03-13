# List of cards with their names and image URLs
# NOTE: start adding descriptions please, we might need them later if we're actually planning on using PIL(the image api thingie) for variable stats
cards = [
    {
        "name": "Dicer",
        "aliases": ["Gamester"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322205863611600896/RobloxScreenShot20241227_145936188.png?ex=677201eb&is=6770b06b&hm=f74d9e756dd8ae25b0c65b6fbdfd169c1c08679912c956c068f75c50171e9b95&=&format=webp&quality=lossless",
        "card_image_url": "https://i.imgur.com/HkUXPJ7.png",
        "rarity": 8.5,  
        "health": 6500,
        "damage": 3500,
        "description": "Retired :-)"
    },
    {
        "name": "Reyes",
        "aliases": ["Kings"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322503928591548482/RobloxScreenShot20241228_105546001.png?ex=67726ec3&is=67711d43&hm=4978a7aa74371952a439ec75fd2ac459bb1f49af739b8ec7d0f6d145c54642d9&=&format=webp&quality=lossless",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1322585956938944512/CC-1598_Reyes_is_the_Marshal_Commander_of_the_235th_Elite_Corps.png?ex=677363e8&is=67721268&hm=35ffd80d26b26c28e60db3da255a071919fa7f0e87c1d8e2aecdd75e65e5031b&",
        "rarity": 0.5,
        "health": 10000,
        "damage": 5000,
        "description": "CC-1598 \"Reyes\" is the Marshal Commander of the 235th Elite Corps. He has led the Corps since the very beginning. His experience, tactical insight and French accent have earned him the trust of his troopers."
    },
    {
        "name": "Sentinel",
        "aliases": ["Senti"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322284693164523520/RobloxScreenShot20241227_202621517.png?ex=67724b55&is=6770f9d5&hm=79e9f8374ffa7b0138f938a11d7916b45ee79b2afdf1fc6c8197c27349b46684&=&format=webp&quality=lossless&width=377&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323317997414121665/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag.png?ex=6774136c&is=6772c1ec&hm=f4d4550607203a12eaa72d7b6a0086efb64bf3d8c623650d713dbf7a96bc242d&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 23,
        "health": 1650,
        "damage": 550,
        "description": "Just another trooper trying to stay alive. He doesn't like insurgents. His left arm and left eye are gone due to the Gulag."
    },
    {
        "name": "Blau",
        "aliases": ["Blue"],
        "spawn_image_url": "https://i.imgur.com/GAipebf.png",
        "card_image_url": "https://i.imgur.com/7gWpCBY.png",
        "rarity": 12.5,
        "health": 6050,
        "damage": 2250,
        "description": "SLEEP."
    },
    {
        "name": "Hounder",
        "aliases": ["Dogger", "Balls"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322295423360176218/RobloxScreenShot20241227_210852940.png?ex=67725553&is=677103d3&hm=c32cad3bc0dc2ebc26cbdfeba7e8fb5ea83b55e557eafbfc3a0358a760654d7e&=&format=webp&quality=lossless",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1327717504570622106/CC-_4.png?ex=678414c8&is=6782c348&hm=1bae24ba790ed2221442f0fea0f118141d22b513dfae442192d5eddf6c9b9689&",
        "rarity": 9.5,
        "health": 9250,
        "damage": 4500,
        "description": "CC-9382 \"Hounder\" is a Senior Commander in the 235th Elite Corps. Hounder himself is a clone who doesn't take his rank too seriously and is mostly chill. Oh, keep an eye on your balls when he is around..."
    },
    {
        "name": "Pipopro",
        "aliases": ["Tux"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1322977622778576976/artworks-OF3WFPHsapfnZrW8-lDiZAQ-t500x500.png?ex=67737f2d&is=67722dad&hm=1ec22c5b9af4c994af583de216afe05660c777e5437a738750577b9a49cbdf90&=&format=webp&quality=lossless",
        "card_image_url": "https://i.imgur.com/4OAxy8x.png",
        "rarity": 0.75,
        "health": 10000,
        "damage": 7500,
        "description": "Was one of the developers before he changed his mind and became a world-class tap dancer, to outdance the dangers of a galaxy far, far away.."
    },
    {
        "name": "Wilson",
        "aliases": ["French"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323344360879689730/RobloxScreenShot20241230_161947936.png?ex=67742bfa&is=6772da7a&hm=14a472045ae47f536705b91cb91bdae7ea52674d1cde2799ad65835c0c85d8df&=&format=webp&quality=lossless&width=532&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1327718322648911984/CC-_5.png?ex=6784158b&is=6782c40b&hm=9f341222aedc8de0679fb89116c2efb8027ae7a9324504af3d0d204edb7359a0&=&format=webp&quality=lossless&width=275&height=385",
        "rarity": 1,
        "health": 9550,
        "damage": 4670,
        "description": "CC-1695, also known as (grandpa) \"Wilson\" is one of the Senior Commanders of the Corps, also known for his ability as a sharpshooter. He always puts his brothers first, and motivates them with his baguettes on the battlefield."
    },
    {
        "name": "Stinger",
        "aliases": ["Pricker", "Ironhide"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323379787766698116/RobloxScreenShot20241230_205740938.png?ex=67744cf8&is=6772fb78&hm=ffe51d5793e02353736175578a9a6158e243b285a65649e695ba924a710c3c83&=&format=webp&quality=lossless&width=375&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323383213451640862/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_13.png?ex=67745029&is=6772fea9&hm=c08cafd74fea97dcd3c7c6847ab940b55249ed62f0585149ca03e05c13ed6ea7&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 75,
        "health": 2150,
        "damage": 950,
        "description": "Dead..."
    },
    {
        "name": "Sandy",
        "aliases": ["Granular"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1328809463808786484/RobloxScreenShot20250114_202141022.png?ex=67cded40&is=67cc9bc0&hm=ffc5380c0d4dcf711286e7ce8487ad98f804b3edf70f6742054ee83378a5e10b&=&format=webp&quality=lossless",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1328809380963024958/Kopie_van_Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_3.png?ex=67cded2c&is=67cc9bac&hm=517a0556055f176fe7f543ae4541d799ad7d9d1f6e69ff6c014eb656d8df2bcb&=&format=webp&quality=lossless",
        "rarity": 50,
        "health": 3000,
        "damage": 1950,
        "description": "Sandy, also known as CT-2457, is a clone engineer in the 31st Shepherd Battalion. He is called Sandy because of his dirty armour on his first mission, which was to Tatooine."
    },
    {
        "name": "Rancor",
        "aliases": ["Rancour"],
        "spawn_image_url": "https://i.imgur.com/7zxapp6.png",
        "card_image_url": "https://i.imgur.com/CjvRccv.png",
        "rarity": 12.5,
        "health": 6950,
        "damage": 3050,
        "description": "Rancor is an adaptable, honest, persistent, understanding, rational, Norwegian and easy-going clone. Missions he takes are mostly all around, as he's well rounded in (almost) everything, and is a good tactician... sort of."
    },
    {
        "name": "Cooker",
        "aliases": ["Boiler"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323570324767379497/RobloxScreenShot20241231_093357795.png?ex=6774fe6c&is=6773acec&hm=c75865e285d3d39f4a6476d442a01c9e1dbe3611a0b06cbd862c8c43b770e956&=&format=webp&quality=lossless&width=468&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323573966652309504/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_17.png?ex=677501d0&is=6773b050&hm=8fe64e466f95254086fd222ad3698819eff00c38d7ab2333f132458ca25af856&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 17.5,
        "health": 5000,
        "damage": 2500,
        "description": "The number one stove! From medic to clone commando to sharpshooter, it is... the STOVE!"
    },
    {
        "name": "Longshot",
        "aliases": ["Shortshot"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323671916631949362/RobloxScreenShot20241231_161614848.png?ex=67755d09&is=67740b89&hm=cab4a3d1dba4eb57b42e592905780faaa24d5ffba9746ce3406325c7f520ef0d&=&format=webp&quality=lossless&width=480&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323671828111298584/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_19.png?ex=67755cf4&is=67740b74&hm=05d5e4c11313875aea75d4c7e227bf32546af435d3755ebac0e66d817c11d2f5&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 70,
        "health": 2000,
        "damage": 650,
        "description": "Not your typical clone has his chip removed and survived in a CIS prison; his last corp died in an ariel bombardment, after this he joined the 235th."
    },
    {
        "name": "Mertho",
        "aliases": ["Merthod"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323578208863649863/RobloxScreenShot20241231_100652348.png?ex=677505c3&is=6773b443&hm=e8aad1e00d28942444ea357afa5b4ce2d0d4cd1949ad84e29fb99aae522be1f8&=&format=webp&quality=lossless&width=384&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323672693647609937/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_21.png?ex=67755dc2&is=67740c42&hm=ddb0d3ac0879577f7497b50ccf367d6fe0afe12850451350bf7b79528dd56b49&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 70,
        "health": 1700,
        "damage": 500,
        "description": "CT-3838, otherwiese known as \"Mertho\" is an irritating jerk, that often ruins missions just because he finds it amusing."
    },
    {
        "name": "Bricker",
        "aliases": ["Legoman"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323674207355404338/RobloxScreenShot20241231_162811051.png?ex=6776b0ab&is=67755f2b&hm=469701c4cfe846ba2a1d409054169e50e4a38f2be05edb25e02bdb1037701ae5&=&format=webp&quality=lossless&width=490&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323983294827597834/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_22.png?ex=67767f07&is=67752d87&hm=7d25ae8c7bbb0d950f02bc65458feec54d1c0d9587801257fc4d6f21f3ef920f&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 85,
        "health": 1550,
        "damage": 450,
        "description": "CT-7171, AKA Bricker, is a brave trooper; he respects his superiors and will always listen to orders. He is very good with an AT-RT"
    },
    {
        "name": "Sinner",
        "aliases": ["Repenter"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323982617527451708/RobloxScreenShot20250101_125340765.png?ex=67767e66&is=67752ce6&hm=57ff065a4ae55a28e1a67ea0dfe6a55959924dd8c7f6c7375c6acb204bfcfb1f&=&format=webp&quality=lossless&width=318&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323984903406354543/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_23.png?ex=67768087&is=67752f07&hm=c2a2e730930dc2aaa552e1aa40e0d4d01c7bc89aea1608b3c5c67319093fae68&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 77,
        "health": 2550,
        "damage": 1755,
        "description": "I aint writing all a that"
    },
    {
        "name": "Voca",
        "aliases": ["Vocabulary"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323987029956235304/RobloxScreenShot20250101_131047926.png?ex=67768282&is=67753102&hm=ec5f28ea32edcadee43190286cc5cdbe0d9197d69142a99813f2bc1e9c8d336f&=&format=webp&quality=lossless",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323988014418104330/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_24.png?ex=6776836d&is=677531ed&hm=f57ab17956ed12fe5e9a1d4a326a09c83794975d06a5e305d386536a988b3c89&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 45,
        "health": 3750,
        "damage": 2050,
        "description": "A veteran of the 31st Shepherd Battalion, skilled marksman, and kind hearted brother of the 235th Elite Corps."
    },
    {
        "name": "Ren'dar Auron",
        "aliases": ["Rendar", "Auron", "GONK"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323993493432959006/RobloxScreenShot20250101_133639131.png?ex=67768887&is=67753707&hm=e2cea043c4cec15a1d0ae8e31b6b03ff8629da7db01ad4d73133d61d4baef63b&=&format=webp&quality=lossless",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323994036050071583/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_25.png?ex=67768908&is=67753788&hm=fd7bf7144407d5691bffc88739a40cdad0f19eb0a61bae6073dd563e9b94a77a&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 25,
        "health": 6500,
        "damage": 2850,
        "description": "A Jedi knight, commanding the 93rd Helios legion alongside Hounder, with the left part of the body completely scarred by an explosion. He had to use cybernetic implants in order to stay alive."
    },
    {
        "name": "Skye",
        "aliases": ["Sky"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1323995408648638475/RobloxScreenShot20250101_134436877.png?ex=67768a50&is=677538d0&hm=bd6dd80b06ef660f4659867b68c4333beb25d7d9a715287f768032dc79951f49&=&format=webp&quality=lossless&width=419&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323996389897797693/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_26.png?ex=67768b3a&is=677539ba&hm=c8013ba4445f32990c4f2e49e7aa7b346cfbaa78a0dac58d820d3acaf847b8b0&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 61,
        "health": 2700,
        "damage": 1500,
        "description": "Brave soldier who follows orders from his superiors and executes them as well as possible."
    },
    {
        "name": "Je'keshi Vale",
        "aliases": ["Jekeshi", "Vale", "Smurf"],
        "spawn_image_url": "https://cdn.discordapp.com/attachments/1322205679028670495/1327722115100835933/RobloxScreenShot20250111_202353810.png?ex=67841914&is=6782c794&hm=7bf5d91914998c58b51b630f24bc248cff0a42389bad4bf3b9d71a4aaf9498a1&",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1327730759452201031/CC-_12.png?ex=67842121&is=6782cfa1&hm=052958065501727e5bc27b03ad171c8617ca998d70a7baecdfa91cebc1562042&",
        "rarity": 7.5,
        "health": 9250,
        "damage": 5500,
        "description": "Femboy jedi general <3",
    },
    {
        "name": "Stars",
        "aliases": ["Twinkletoes" ], #dont ask why, what, how, where or when
        "spawn_image_url": "https://cdn.discordapp.com/attachments/1322205679028670495/1327722697647456336/RobloxScreenShot20250111_203536461.png?ex=6784199f&is=6782c81f&hm=ce4fbdf5b8cf708d7fbec195863fdff44e799a322aeaaab456135d17a3a3d078&",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1327723966873210950/CC-_8.png?ex=67841acd&is=6782c94d&hm=139ff0e1661f647c03b15892c4834a8d8e6c8ebcd76b30688df4397366d3279f&", 
        "rarity": 8.5,
        "health": 6250,
        "damage": 3250,
        "description": "ARC Commander Stars is a member within the GAR, serving alongside Commanders like Reyes, Hounder and Wilson. He currently leads the 31st \"Shepherd\" Battalion in the 235th Elite Corps.",   
    },
    {
        "name": "Ringo",
        "aliases": ["Rhino"],
        "spawn_image_url": "https://cdn.discordapp.com/attachments/1322205679028670495/1327727582355001415/RobloxScreenShot20250111_205428565.png?ex=67841e2b&is=6782ccab&hm=023f2e1e782f8fb00cbdfa6b3603ec2b4d669777d5b2068d1884ad48f65f7b26&",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1327729546556084244/CC-_11.png?ex=67841fff&is=6782ce7f&hm=bed1ee961a06e1bd8803e8af6e8cb753e23990c71e7a8fdcab93e09aa6f4c039&",
        "rarity": 68,
        "health": 1750,
        "damage": 900,
        "description": "Probably one of the least efficient members of the 235th, always finds a way to get in trouble and injure himself. Has a pet croc named Romeo that sometimes comes with him",
    },
    {
        "name": "Rush",
        "aliases": ["Hurry"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1328442857547235368/RobloxScreenShot20250113_201710741.png?ex=67876112&is=67860f92&hm=8f4fcde3e4deda60ddc8e3e2d95c2a4a418fd7b540556e6ca6c67681cc9138b1&=&format=webp&quality=lossless",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1328443617282494615/Kopie_van_Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag.png?ex=678761c7&is=67861047&hm=24861f0d3535e56d30d6fafa7a6aed0f5f9c9abd1fcae16742072ce550c8563d&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 82,
        "health": 1500,
        "damage": 450,
        "description": "PFC. \"Rush\" is a clone tropper who serves under the GAR and the 235th Elite Corp, he might be known as the GEneral Carrier",
    },
    {
        "name": "Breaker",
        "aliases": ["Hawk"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1328445706154803231/RobloxScreenShot20250113_202833195.png?ex=678763b9&is=67861239&hm=665929510234995d9d4de2c0ec421619b207d7dcc560376cf34e36caa268c835&=&format=webp&quality=lossless&width=448&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1328445432933781525/Kopie_van_Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_1.png?ex=67876378&is=678611f8&hm=48b5fd84fcbbda4ea8caec9be1c1840bdda674a8acace2a0e4f869f549b2321f&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 40,
        "health": 6000,
        "damage": 3000,
        "description": "\"Breaker\" is an ex Ri and now a hawk squad member, he has a bunch of skills and tactics to be used.",
    },
    {
        "name": "Micro",
        "aliases": ["Macro"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1328436322905620510/RobloxScreenShot20250113_195110065.png?ex=678803bc&is=6786b23c&hm=893e4062e2ff369eea65b1db416f3adeadf14894776774b44b3ee3e41e0a4a8a&=&format=webp&quality=lossless&width=525&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1328446048921976922/CC-.png?ex=6787640b&is=6786128b&hm=68d9429e31af06d9e8d0459864ca1aed71174aa23391c565d1859aa9368500b6&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 30,
        "health": 6100,
        "damage": 3500,
        "description": "\"Micro\" is an expert on stealth and specialised in missions. He can aim very well and hits almost every droid. He also is a S!gM@."
    },
    {
        "name": "Zak",
        "aliases": ["Tas", "gekolonieseerd"],
        "spawn_image_url": "https://i.imgur.com/qEPznfk.png",
        "card_image_url": "https://cdn.discordapp.com/attachments/1322202570529177642/1328808412540047370/Kopie_van_Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_2.png?ex=6788b585&is=67876405&hm=85d4507f20ecb0ec90be7842616cf049fadcc8784d87da71fd6c5e5ea03bcb36&",
        "rarity": 15,
        "health": 6000,
        "damage": 3000,
        "description": "\"Zak\" is an ex Ri and now a member of the 82nd \"Marshal\" platoon. He also likes hamburgers and is a very cool dutchman."
    },
    {
        "name": "Hollow",
        "aliases": ["Gollow"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1324449804008296453/RobloxScreenShot20250102_195006907.png?ex=678df240&is=678ca0c0&hm=bad958251fad83f01cbb88f66e122ac143410c38c8355c88b5acadcffb5314e4&=&format=webp&quality=lossless&width=470&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1324451870688804874/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_29.png?ex=678df42d&is=678ca2ad&hm=80f5e71b4642955de3ec209b8f66bf0a394d64bcfe54d643ab7d7e66bdf4eeef&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 59,
        "health": 6000,
        "damage": 3150,
        "description": "Who's the squad leader? guy that's extremely stacked or a painted normal commando?"
    },
    {
        "name": "Vic",
        "aliases": ["Victory"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1324445639840501820/RobloxScreenShot20250102_193103800.png?ex=678dee5f&is=678c9cdf&hm=ee4ac8eaef170ba6a8ff6f7f249c2d3363e7a0049cbe525284cb6a74885a3762&=&format=webp&quality=lossless&width=467&height=350",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1324446784390696960/Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_27.png?ex=678def70&is=678c9df0&hm=27558b2cd751b612ab68f27ea4e6f55432e71264a88fe7e97739a03c132ae780&=&format=webp&quality=lossless&width=479&height=671",
        "rarity": 65,
        "health": 2150,
        "damage": 1100,
        "description": "Member of Helios legion, 14th Alshemy Platoon, Platoon Executive, Corporal, and of course, A FRENCH AAAAAH"
    },
    {
        "name": "Apok",
        "aliases": ["Apuk"],
        "spawn_image_url": "https://media.discordapp.net/attachments/1322205679028670495/1324655419330793472/RobloxScreenShot20250103_092524172.png?ex=678e08fe&is=678cb77e&hm=732e157dba57b0b80bdcadb61d986b35dc1b783eda259e7316e06df8c85d5ce8&=&format=webp&quality=lossless",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1324666151695028296/Kopie_van_Just_another_trooper_trying_to_stay_alive._He_doesnt_like_insurgents._His_left_arm_and_left_eye_are_gone_due_to_the_Gulag_1.png?ex=678e12fd&is=678cc17d&hm=920544f07533267627011830f7226059473d0e1ab85032c892d61d5535447b3f&=&format=webp&quality=lossless&width=250&height=350",
        "rarity": 46,
        "health": 3200,
        "damage": 2150,
        "description": "Goofy dishwasher in the kitchen crew",
    },
    {
        "name": "Sharpeye",
        "aliases": ["Sharpie", "triggerboy"],
        "spawn_image_url": "https://i.imgur.com/EKCz1Ly.png",
        "card_image_url": "https://i.imgur.com/mjEypbU.png",
        "rarity": 89,
        "health": 1200,
        "damage": 550,
        "description": "Going prone, aiming, and pulling the trigger. Target eliminated."
    },
    {
        "name": "Sparrow",
        "aliases": ["Bird", "flappy bird"],
        "spawn_image_url": "https://i.imgur.com/XOMm3Hk.png",
        "card_image_url": "https://i.imgur.com/SKzXcaz.png",
        "rarity": 60,
        "health": 2600,
        "damage": 1700,
        "description": "The best ever pilot in all of spitfire (says sparrow himself) breaker and fragger hate him."
    },
    {
        "name": "Worst",
        "aliases": ["rookworst", ],
        "spawn_image_url": "https://i.imgur.com/hGmZJFv.png",
        "card_image_url": "https://i.imgur.com/5uvUBdW.png",
        "rarity": 86,
        "health": 1500,
        "damage": 750,
        "description": "After a training disaster, his sergeant called him 'Worst' a failing marksman."
    },
    {
        "name": "Sigma-squad",
        "aliases": ["eaglesmademedothis", "whydidiagreetothis","sigma squad"],
        "spawn_image_url": "https://cdn.discordapp.com/attachments/1322205679028670495/1323215414393700455/RobloxScreenShot20241230_100007909.png?ex=67a086e2&is=679f3562&hm=cf9521fb29329e7ab81f84548e9c0664566adc9dccac4bc549b1d0e8cd70f166&",
        "card_image_url": "https://media.discordapp.net/attachments/1322202570529177642/1323215495637504010/Pipopro_1.png?ex=67a086f6&is=679f3576&hm=a95177683cf7782138009565d2c8952c9d53482146ac5be7d829375fb03becf8&=&format=webp&quality=lossless&width=358&height=502",
        "rarity": 0,
        "health": 1,
        "damage": 10000000000000000000000000000,
        "description": "They might be sigma, but they are definitely not the best squad."
    },
    {
        "name": "Hades",
        "aliases": ["Fiery Furnace Fred", "Grim Gramps"],
        "spawn_image_url": "https://i.imgur.com/ZyrxWzY.png",
        "card_image_url": "https://i.imgur.com/tJQu2dZ.png",
        "rarity": 67,
        "health": 2900,
        "damage": 1700,
        "description": "You know that one guy who thinks he's the main character but really isn't? Well, that's Hades right there!"
    },
    {
        "name": "Mixer",
        "aliases": ["Blender", "existence", "dutchman" ], #mixer verzin er zelf is een paar leuke
        "spawn_image_url": "https://i.imgur.com/ULt5mqn.png",
        "card_image_url": "https://i.imgur.com/BxW3vdm.png",
        "rarity": 30,
        "health": 5800,
        "damage": 2000,
        "description": "A wild Mixer proves: Existence is mandatory!",
    },
    {
        "name": "Eagles",
        "aliases": ["eagly"],
        "spawn_image_url": "https://i.imgur.com/DQRyj4F.png",
        "card_image_url": "https://i.imgur.com/iBIbwEr.png",
        "rarity": 30,
        "health": 5700,
        "attack": 2100,
        "description": "ARC-1717, Better known as Eagles, is a persistent and experienced clone trooper. He fought many battles, and he cares about his brothers.",
    },
    {
        "name":"Sanghelios",
        "aliases": ["Sangheli"],
        "spawn_image_url": "https://i.imgur.com/JwKNNKh.png",
        "card_image_url": "https://i.imgur.com/7Yr4VUU.png",
        "rarity": 31,
        "health": 6100,
        "damage": 2000,
        "description": "Current Director of RI Clone Sergeant Sanghelios of the Republic Intelligence 235th attachement, highly skilled in stealth and disguise along with the essentials for a trooper."
    },
]