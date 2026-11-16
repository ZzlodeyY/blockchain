const MMMsisToken = artifacts.require("MMMsisToken");
const MMMsisAccess = artifacts.require("MMMsisAccess");

module.exports = async function (deployer, network, accounts) {
  await deployer.deploy(MMMsisToken, { from: accounts[0] });
  const token = await MMMsisToken.deployed();

  await deployer.deploy(MMMsisAccess, token.address, { from: accounts[0] });
};
